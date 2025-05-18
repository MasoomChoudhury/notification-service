import logging
import uuid
import os # Added for path operations
from contextlib import asynccontextmanager
from datetime import datetime

import aio_pika
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status as http_status
from fastapi.responses import JSONResponse, FileResponse # Added FileResponse
from fastapi.middleware.cors import CORSMiddleware # Added CORSMiddleware
# from fastapi.staticfiles import StaticFiles # Optional: if serving a directory

from app.config import settings
from app import database, queue, models

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application startup...")
    
    # Initialize Database
    try:
        # Ensure the db_data directory exists (where SQLite file will be)
        db_dir = os.path.dirname(database.DATABASE_URL)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"Created database directory: {db_dir}")

        await database.create_tables() 
        logger.info("Database tables initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        raise 

    # Initialize RabbitMQ Connection and Channel
    try:
        app.state.rabbitmq_connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        app.state.rabbitmq_channel = await app.state.rabbitmq_connection.channel()
        await queue.declare_queue(app.state.rabbitmq_channel, settings.RABBITMQ_QUEUE_NAME)
        logger.info("RabbitMQ connection, channel, and queue initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize RabbitMQ: {e}")
        raise 

    yield

    # Shutdown
    logger.info("Application shutdown...")
    if hasattr(app.state, 'rabbitmq_channel') and app.state.rabbitmq_channel and not app.state.rabbitmq_channel.is_closed:
        await app.state.rabbitmq_channel.close()
        logger.info("RabbitMQ channel closed.")
    if hasattr(app.state, 'rabbitmq_connection') and app.state.rabbitmq_connection and not app.state.rabbitmq_connection.is_closed:
        await app.state.rabbitmq_connection.close()
        logger.info("RabbitMQ connection closed.")


app = FastAPI(
    title="Notification Service",
    version="0.1.0",
    description="A service to send Email, SMS, and In-App notifications.",
    lifespan=lifespan
)

# Add CORS middleware
# Allows requests from any origin, specific origins can be configured for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Or specify origins like ["http://localhost:8000", "http://127.0.0.1:8000"]
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)

# API Router
api_router = APIRouter(prefix=settings.API_BASE_PATH)

async def get_mq_channel() -> aio_pika.abc.AbstractChannel:
    if not hasattr(app.state, 'rabbitmq_channel') or app.state.rabbitmq_channel.is_closed:
        logger.error("RabbitMQ channel not available or closed in app.state.")
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Message queue service is not available at the moment."
        )
    return app.state.rabbitmq_channel


@api_router.post("/notifications",
             status_code=http_status.HTTP_202_ACCEPTED,
             response_model=models.NotificationResponse,
             summary="Queue a new notification")
async def create_notification(
    notification_req: models.NotificationRequest,
    mq_channel: aio_pika.abc.AbstractChannel = Depends(get_mq_channel)
):
    notification_id = uuid.uuid4()
    now = datetime.utcnow()

    current_status = models.NotificationStatusEnum.PENDING
    if notification_req.send_at and notification_req.send_at > now:
        current_status = models.NotificationStatusEnum.SCHEDULED
    
    notification_db_data = models.NotificationDB(
        id=notification_id,
        created_at=now,
        updated_at=now,
        status=current_status,
        **notification_req.dict()
    )

    try:
        async with database.get_db_connection() as db_conn:
            await database.insert_notification(db_conn, notification_db_data)
            try:
                await queue.publish_message(
                    mq_channel,
                    settings.RABBITMQ_QUEUE_NAME,
                    notification_db_data.dict()
                )
            except Exception as mq_exc:
                logger.error(f"MQ Publishing error after DB insert for {notification_id}: {mq_exc}. Rolling back DB.")
                await db_conn.rollback() # Rollback DB if MQ fails
                raise HTTPException(
                    status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Failed to publish notification to queue after database operation. Transaction rolled back."
                )
            await db_conn.commit()
        
        logger.info(f"Notification {notification_id} successfully queued. Status: {notification_db_data.status.value}")
        return models.NotificationResponse(
            message="Notification queued successfully.",
            notificationId=notification_id
        )
    except database.sqlite3.IntegrityError as e:
        logger.error(f"Database integrity error for notification {notification_id}: {e}")
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"Database integrity error: {str(e)}")
    except aio_pika.exceptions.AMQPError as e: # More specific AMQP error
        logger.error(f"RabbitMQ publishing error for notification {notification_id}: {e}")
        # DB transaction should have been rolled back if this occurs after insert attempt
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to publish notification to queue.")
    except Exception as e:
        logger.error(f"Unexpected error creating notification {notification_id}: {e}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@api_router.get("/health", summary="Health check endpoint")
async def health_check():
    return {"status": "ok"}

# --- Endpoints for SNS Push Subscriptions ---

@api_router.post("/users/{user_id}/android-sns-subscriptions",
                  status_code=http_status.HTTP_201_CREATED,
                  response_model=models.SnsPushSubscriptionDB, # Or a specific response model
                  summary="Register an Android device's FCM token with AWS SNS")
async def register_android_device_for_sns_push(
    user_id: str,
    subscription_req: models.SnsPushSubscriptionCreate,
    # db_conn: aiosqlite.Connection = Depends(database.get_db_connection) # If using Depends for DB
):
    """
    Registers an FCM token for a user with AWS SNS to enable push notifications.
    This involves creating a platform endpoint in SNS.
    """
    if subscription_req.user_id != user_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="User ID in path does not match user ID in request body."
        )

    from app.providers import push_sns_provider # Import here to avoid circular dependency issues at module load
    
    endpoint_arn = await push_sns_provider.create_sns_platform_endpoint_async(
        fcm_token=subscription_req.fcm_token,
        user_id=user_id
    )

    if not endpoint_arn:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create platform endpoint with SNS."
        )

    subscription_db = models.SnsPushSubscriptionDB(
        user_id=user_id,
        fcm_token=subscription_req.fcm_token,
        endpoint_arn=endpoint_arn
        # id, platform, is_enabled, created_at, updated_at will use defaults or be set by add_sns_push_subscription
    )
    
    try:
        async with database.get_db_connection() as db_conn:
            created_subscription = await database.add_sns_push_subscription(db_conn, subscription_db)
            await db_conn.commit()
        return created_subscription
    except database.sqlite3.IntegrityError as e: # e.g. UNIQUE constraint on endpoint_arn
        logger.error(f"Database integrity error registering SNS subscription for user {user_id}: {e}")
        # This might happen if another request created the same endpoint_arn just before commit.
        # Or if fcm_token + user_id should be unique and handled differently.
        # For now, a generic conflict.
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Failed to save subscription due to a conflict: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error saving SNS subscription for user {user_id}: {e}")
        # Potentially try to delete the SNS endpoint if DB save fails to keep things clean
        # await push_sns_provider.delete_sns_platform_endpoint_async(endpoint_arn)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save push notification subscription."
        )

@api_router.delete("/users/{user_id}/android-sns-subscriptions/{endpoint_arn}",
                   status_code=http_status.HTTP_204_NO_CONTENT,
                   summary="Unregister an Android device from AWS SNS push notifications")
async def unregister_android_device_from_sns_push(
    user_id: str, # Can be used for validation if needed, e.g., ensuring endpoint_arn belongs to user
    endpoint_arn: str
):
    """
    Deletes an SNS platform endpoint and its corresponding subscription from the database.
    """
    from app.providers import push_sns_provider

    # First, try to delete from SNS
    sns_delete_success = await push_sns_provider.delete_sns_platform_endpoint_async(endpoint_arn)
    
    if not sns_delete_success:
        # Log the error but still attempt to delete from local DB if desired,
        # or raise an error if SNS deletion is critical before DB deletion.
        logger.warning(f"Failed to delete endpoint {endpoint_arn} from SNS, but will attempt to delete from local DB.")
        # Depending on policy, you might raise HTTPException here.

    try:
        async with database.get_db_connection() as db_conn:
            db_delete_success = await database.delete_sns_push_subscription_by_endpoint_arn(db_conn, endpoint_arn)
            await db_conn.commit()

        if not db_delete_success and sns_delete_success:
            # SNS deleted but not found in DB - inconsistent state, but operation "succeeded" from client perspective for SNS part
            logger.warning(f"Endpoint {endpoint_arn} deleted from SNS but not found in local DB.")
            # No error to client as SNS part was the main goal.
            return
        elif not db_delete_success and not sns_delete_success:
             raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, # Or 500 if SNS failed earlier
                detail="Push notification subscription endpoint not found in SNS or local database."
            )
        # If db_delete_success, return 204 implicitly
    except Exception as e:
        logger.error(f"Unexpected error deleting SNS subscription for endpoint {endpoint_arn} from DB: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete push notification subscription from database."
        )

# Pydantic model for the contact owner request
class ContactOwnerRequest(models.BaseModel):
    contact_detail: str

@api_router.post("/contact-owner",
                  status_code=http_status.HTTP_202_ACCEPTED,
                  summary="Send contact detail to project owner via Textbee SMS")
async def contact_project_owner(
    request_data: ContactOwnerRequest,
    mq_channel: aio_pika.abc.AbstractChannel = Depends(get_mq_channel)
):
    owner_phone_number = "+918249019575" # Your primary phone number
    message_to_owner = f"Recruiter contact for testing: {request_data.contact_detail}"
    notification_id = uuid.uuid4()
    now = datetime.utcnow()

    notification_db_data = models.NotificationDB(
        id=notification_id,
        created_at=now,
        updated_at=now,
        status=models.NotificationStatusEnum.PENDING,
        channel=models.ChannelEnum.SMS,
        sms_provider=models.SmsProviderEnum.TEXTBEE, # Always use Textbee for this
        recipient_phone=owner_phone_number,
        message_body=message_to_owner
    )

    try:
        async with database.get_db_connection() as db_conn:
            await database.insert_notification(db_conn, notification_db_data)
            try:
                await queue.publish_message(
                    mq_channel,
                    settings.RABBITMQ_QUEUE_NAME,
                    notification_db_data.dict()
                )
            except Exception as mq_exc:
                logger.error(f"MQ Publishing error for contact-owner notification {notification_id}: {mq_exc}. Rolling back DB.")
                await db_conn.rollback()
                raise HTTPException(
                    status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Failed to publish contact-owner notification to queue after database operation. Transaction rolled back."
                )
            await db_conn.commit()
        
        logger.info(f"Contact-owner notification {notification_id} successfully queued to {owner_phone_number}.")
        return {"message": "Contact detail has been sent to the project owner."}
    except Exception as e:
        logger.error(f"Unexpected error processing contact-owner request for {notification_id}: {e}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while processing your request.")

app.include_router(api_router)

# Route to serve the frontend.html
# Ensure 'static' directory is at the same level as this main.py if running directly,
# or at the project root if Docker context is project root.
# For Docker, the path should be relative to the Docker container's file system.
# If Dockerfile copies 'static' to '/app/static', then path is "static/frontend.html"
# If Dockerfile copies 'static' to '/static', then path is "/static/frontend.html"
# Assuming 'static' is at the project root and Docker context is project root,
# and 'static' is copied to '/app/static' in Dockerfile (or mounted there).
# For simplicity, let's assume the 'static' folder is at the root of the project
# and the Dockerfile copies it into the app's working directory.
# If the Docker working dir is /app, and static is copied to /app/static:
STATIC_DIR = "static" 
# If running locally without Docker, and static is at project root:
# STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static") # if main.py is in app/
# For Docker, if static is at project root and copied to /app/static:
# STATIC_DIR = "/app/static" # This might be more robust in Docker if WORKDIR is /app

@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_frontend():
    # Path relative to where FastAPI app is running.
    # If Docker WORKDIR is /app, and static is copied to /app/static:
    frontend_path = os.path.join(STATIC_DIR, "frontend.html")
    
    # A more robust way if main.py is in app/ and static/ is at project root:
    # project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # frontend_path = os.path.join(project_root, "static", "frontend.html")
    # However, for Docker, it's simpler if paths are relative to WORKDIR or absolute in container.

    # Assuming 'static' directory is at the same level as the 'app' directory (project root)
    # and the Dockerfile correctly copies 'static' into the image, or it's mounted.
    # If WORKDIR is /app, and static is at project root, it might be ../static/frontend.html
    # Let's assume for Docker, 'static' is copied to be alongside 'app' module inside /app
    # So, if main.py is /app/app/main.py, then static is /app/static/frontend.html
    
    # Simplest for Docker if static is copied to /app/static:
    # frontend_path = "static/frontend.html" 
    # If static is at project root and WORKDIR is /app, and app code is in /app/app:
    # This assumes the 'static' folder is at the root of the project,
    # and the Docker container's working directory is /app.
    # The Dockerfile should copy the 'static' folder to '/app/static'.
    
    # Let's assume the `static` directory is at the project root,
    # and our Dockerfile copies it to `/app/static`.
    # The current working directory in the container is `/app`.
    # So the path from `/app` to `/app/static/frontend.html` is `static/frontend.html`.
    
    # Path for FileResponse should be relative to where the app is run or absolute.
    # If static is at project root, and app is run from project root (e.g. uvicorn app.main:app)
    # path = "static/frontend.html"
    
    # If app is run from app/ (e.g. uvicorn main:app from within app/)
    # path = "../static/frontend.html"

    # For Docker, if WORKDIR is /app and static is copied to /app/static
    path_to_frontend = "static/frontend.html"
    if not os.path.exists(path_to_frontend):
        # Fallback for local dev where main.py might be in app/
        # and static/ is at project root (../static)
        alt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "frontend.html")
        if os.path.exists(alt_path):
            path_to_frontend = alt_path
        else:
            logger.error(f"frontend.html not found at {path_to_frontend} or {alt_path}")
            raise HTTPException(status_code=404, detail="Frontend not found")
            
    return FileResponse(path_to_frontend)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
