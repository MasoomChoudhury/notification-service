import logging
import asyncio
import boto3
import json
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from typing import Optional, Dict, Any, List

from app.config import settings
from app.models import SnsPushSubscriptionDB # For type hinting if needed

logger = logging.getLogger(__name__)

def _get_sns_client():
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        logger.error("AWS credentials (access key or secret key) are not configured for SNS Push.")
        return None
    if not settings.AWS_REGION_NAME:
        logger.error("AWS Region Name is not configured for SNS Push.")
        return None
    
    return boto3.client(
        "sns",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME
    )

async def create_sns_platform_endpoint_async(fcm_token: str, user_id: Optional[str] = None) -> Optional[str]:
    """
    Creates a platform endpoint in AWS SNS for a given FCM token.
    Returns the EndpointArn if successful, else None.
    """
    sns_client = await asyncio.to_thread(_get_sns_client)
    if not sns_client:
        return None

    if not settings.SNS_PLATFORM_APPLICATION_ARN_ANDROID:
        logger.error("SNS_PLATFORM_APPLICATION_ARN_ANDROID is not configured. Cannot create endpoint.")
        return None

    custom_user_data = f"user_id:{user_id}" if user_id else "general_subscription"

    try:
        logger.info(f"Creating SNS platform endpoint for FCM token (ending ...{fcm_token[-10:]}) for user {user_id}")
        response = await asyncio.to_thread(
            sns_client.create_platform_endpoint,
            PlatformApplicationArn=settings.SNS_PLATFORM_APPLICATION_ARN_ANDROID,
            Token=fcm_token,
            CustomUserData=custom_user_data
            # Attributes={'Enabled': 'true'} # Default is true
        )
        endpoint_arn = response.get("EndpointArn")
        if endpoint_arn:
            logger.info(f"Successfully created SNS platform endpoint: {endpoint_arn} for user {user_id}")
            return endpoint_arn
        else:
            logger.error(f"Failed to create SNS platform endpoint for user {user_id}. Response: {response}")
            return None
    except ClientError as e:
        # Handle common errors, e.g., if token is invalid or endpoint already exists for this token
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "InvalidParameter" and "already exists with the same Token" in str(e):
            # This means the token is already registered. We might need to retrieve the existing EndpointArn.
            # This part can be complex as you need to parse the message to get the existing ARN.
            # For simplicity now, we log it. A robust implementation would fetch/update existing.
            logger.warning(f"FCM token for user {user_id} already registered with SNS. Error: {e}")
            # Potentially try to extract existing ARN from error message or re-enable if disabled.
        else:
            logger.error(f"AWS SNS API error creating platform endpoint for user {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating SNS platform endpoint for user {user_id}: {e}")
        return None

async def delete_sns_platform_endpoint_async(endpoint_arn: str) -> bool:
    """Deletes an SNS platform endpoint."""
    sns_client = await asyncio.to_thread(_get_sns_client)
    if not sns_client:
        return False
    try:
        logger.info(f"Deleting SNS platform endpoint: {endpoint_arn}")
        await asyncio.to_thread(sns_client.delete_endpoint, EndpointArn=endpoint_arn)
        logger.info(f"Successfully deleted SNS platform endpoint: {endpoint_arn}")
        return True
    except ClientError as e:
        logger.error(f"AWS SNS API error deleting platform endpoint {endpoint_arn}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting SNS platform endpoint {endpoint_arn}: {e}")
        return False

async def send_push_notification_async(
    endpoint_arn: str,
    title: Optional[str],
    body: str, # Assuming body is the main message content
    data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Sends a push notification to a specific SNS EndpointArn.
    """
    sns_client = await asyncio.to_thread(_get_sns_client)
    if not sns_client:
        return False

    # Construct the GCM/FCM payload for SNS
    gcm_payload = {"notification": {}}
    if title:
        gcm_payload["notification"]["title"] = title
    if body:
        gcm_payload["notification"]["body"] = body
    
    if data:
        gcm_payload["data"] = data
    
    # If only data is provided (silent push), notification block might be omitted by FCM
    # but SNS requires a message. If no title/body, use a default or ensure body is always present.
    if not title and not body and data: # Data-only push
         # FCM might not show this if 'notification' is empty, but SNS needs a message.
         # For data-only, often a 'content_available: true' is used in FCM payload.
         # This part needs careful crafting based on how client app handles data-only pushes.
         # For now, ensure there's at least a body for SNS.
        logger.warning("Sending push with only data payload. Ensure client app handles this.")
        if not body: # If body was also None
            gcm_payload["notification"]["body"] = "You have a new update." # Default if no body

    message_for_sns = json.dumps({"GCM": json.dumps(gcm_payload)})

    try:
        logger.info(f"Attempting to send SNS push to EndpointArn: {endpoint_arn}")
        logger.debug(f"SNS Push Payload for GCM: {message_for_sns}")

        response = await asyncio.to_thread(
            sns_client.publish,
            TargetArn=endpoint_arn,
            Message=message_for_sns,
            MessageStructure='json'
        )
        message_id = response.get('MessageId')
        if message_id:
            logger.info(f"SNS push successfully published to {endpoint_arn}. MessageID: {message_id}")
            return True
        else:
            logger.error(f"Failed to send SNS push to {endpoint_arn}. No MessageId in response: {response}")
            return False
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "EndpointDisabled":
            logger.warning(f"SNS Endpoint {endpoint_arn} is disabled. Consider removing from DB or re-enabling.")
            # Here you might want to call a function to disable/delete the endpoint_arn in your database
        else:
            logger.error(f"AWS SNS API error sending push to {endpoint_arn}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending SNS push to {endpoint_arn}: {e}")
        return False
