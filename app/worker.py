import asyncio
import json
import logging
import uuid # For type hinting if needed, though id comes from message
from typing import Optional # Added for type hinting
import asyncio # For asyncio.to_thread

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app import database, queue, models, email_service, sms_service
from app.providers import push_sns_provider # Added for PUSH_ANDROID

# Configure basic logging for the worker
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s') # Changed level to DEBUG
logger = logging.getLogger("NotificationWorker")

async def process_notification_message(message: AbstractIncomingMessage):
    """
    Processes a single notification message from RabbitMQ.
    - Deserializes the message.
    - Logs the received notification.
    - Updates the notification status in SQLite to PROCESSING_STUB.
    - Acknowledges the message.
    """
    try:
        logger.info(f"Received message. Delivery tag: {message.delivery_tag}")
        message_body_str = message.body.decode()
        logger.debug(f"Raw message body: {message_body_str[:500]}") # Log snippet of raw body

        notification_data = json.loads(message_body_str)
        
        # Validate with Pydantic model (optional but good practice)
        try:
            notification_message = models.NotificationMessage(**notification_data)
            notification_id_str = str(notification_message.id) # Use ID from validated model
            logger.info(f"Processing notification ID: {notification_id_str}, Channel: {notification_message.channel.value}")
        except Exception as pydantic_exc:
            logger.error(f"Pydantic validation error for message: {pydantic_exc}. Body: {message_body_str[:500]}")
            await message.nack(requeue=False) # Discard message if it's malformed
            return

        sent_successfully = False
        final_status = models.NotificationStatusEnum.PROCESSING_STUB # Default status

        if notification_message.channel == models.ChannelEnum.EMAIL:
            if not notification_message.recipient_email or not notification_message.subject:
                logger.error(f"Missing recipient_email or subject for EMAIL notification ID {notification_id_str}. Marking as FAILED.")
                final_status = models.NotificationStatusEnum.FAILED
            else:
                sent_successfully = await email_service.send_email_async(
                    recipient_email=notification_message.recipient_email,
                    subject=notification_message.subject,
                    text_body=notification_message.message_body,
                    html_body=notification_message.message_html
                )
                if sent_successfully:
                    logger.info(f"Email for notification ID {notification_id_str} sent successfully via MailHog.")
                    final_status = models.NotificationStatusEnum.SENT
                else:
                    logger.error(f"Failed to send email for notification ID {notification_id_str} via MailHog.")
                    final_status = models.NotificationStatusEnum.FAILED
        
        elif notification_message.channel == models.ChannelEnum.SMS:
            # sms_provider check is now implicitly handled by the NotificationRequest model's validator
            # and the dispatcher in sms_service will also check.
            # The credential checks are now within the dispatcher or individual provider modules.
            sent_successfully = await sms_service.send_sms_message(notification_message)
            if sent_successfully:
                logger.info(f"SMS for notification ID {notification_id_str} processed successfully by provider {notification_message.sms_provider.value if notification_message.sms_provider else 'N/A'}.")
                final_status = models.NotificationStatusEnum.SENT
            else:
                logger.error(f"Failed to send SMS for notification ID {notification_id_str} via provider {notification_message.sms_provider.value if notification_message.sms_provider else 'N/A'}.")
                final_status = models.NotificationStatusEnum.FAILED

        elif notification_message.channel == models.ChannelEnum.PUSH_ANDROID:
            if not notification_message.user_id:
                logger.error(f"user_id missing for PUSH_ANDROID notification ID {notification_id_str}. Marking as FAILED.")
                final_status = models.NotificationStatusEnum.FAILED
            elif not settings.SNS_PLATFORM_APPLICATION_ARN_ANDROID:
                 logger.error(f"SNS_PLATFORM_APPLICATION_ARN_ANDROID not configured. Cannot send PUSH_ANDROID for notification ID {notification_id_str}. Marking as FAILED.")
                 final_status = models.NotificationStatusEnum.FAILED
            else:
                async with database.get_db_connection() as db_conn: # Separate connection for this block
                    subscriptions = await database.get_sns_push_subscriptions_by_user_id(db_conn, notification_message.user_id)
                
                if not subscriptions:
                    logger.warning(f"No active PUSH_ANDROID subscriptions found for user_id {notification_message.user_id} (notification ID {notification_id_str}). Marking as FAILED.")
                    final_status = models.NotificationStatusEnum.FAILED
                else:
                    push_results = []
                    for sub in subscriptions:
                        if sub.endpoint_arn and sub.is_enabled:
                            logger.info(f"Sending PUSH_ANDROID to endpoint {sub.endpoint_arn} for user {notification_message.user_id}, notification {notification_id_str}")
                            success = await push_sns_provider.send_push_notification_async(
                                endpoint_arn=sub.endpoint_arn,
                                title=notification_message.push_title,
                                body=notification_message.message_body, # Using message_body as push body
                                data=notification_message.push_data
                            )
                            push_results.append(success)
                            if not success:
                                logger.error(f"Failed to send PUSH_ANDROID to endpoint {sub.endpoint_arn} for notification {notification_id_str}")
                                # Optionally, handle endpoint disabling here based on error from send_push_notification_async
                                # e.g., if EndpointDisabled error, call database.disable_sns_push_subscription_by_endpoint_arn
                        else:
                            logger.warning(f"Skipping disabled or invalid subscription for user {notification_message.user_id}: endpoint_arn={sub.endpoint_arn}")
                    
                    if not push_results: # No valid subscriptions to even attempt
                        final_status = models.NotificationStatusEnum.FAILED
                        logger.warning(f"No valid/enabled PUSH_ANDROID subscriptions attempted for user_id {notification_message.user_id} (notification ID {notification_id_str}).")
                    elif all(push_results):
                        final_status = models.NotificationStatusEnum.SENT
                        logger.info(f"All PUSH_ANDROID notifications for ID {notification_id_str} sent successfully.")
                    else: # Partial success or all failed
                        final_status = models.NotificationStatusEnum.FAILED # Or a new PARTIAL_FAILURE status
                        logger.error(f"One or more PUSH_ANDROID notifications failed for ID {notification_id_str}.")
        
        elif notification_message.channel == models.ChannelEnum.IN_APP:
            logger.info(f"IN_APP notification ID {notification_id_str}. Marking as PROCESSING_STUB (actual logic TBD).")
            final_status = models.NotificationStatusEnum.PROCESSING_STUB 
        
        else:
            logger.warning(f"Unknown channel {notification_message.channel.value} for notification ID {notification_id_str}. Marking as FAILED.")
            final_status = models.NotificationStatusEnum.FAILED

        async with database.get_db_connection() as db_conn:
            try:
                updated = await database.update_notification_status(
                    db_conn,
                    notification_id=notification_message.id, 
                    status=final_status # Use the determined final_status
                )
                await db_conn.commit() 
                if not updated:
                    logger.warning(f"Notification ID {notification_id_str} not found in DB or not updated to {final_status.value}.")
                else:
                    logger.info(f"Notification ID {notification_id_str} status updated to {final_status.value} in DB.")
                
                await message.ack() 
                logger.info(f"Message for notification ID {notification_id_str} acknowledged.")
            except database.sqlite3.Error as db_exc:
                logger.error(f"Database error processing notification {notification_id_str}: {db_exc}. Rolling back.")
                await db_conn.rollback()
                await message.nack(requeue=True) 
                return 
            except Exception as e_inner: 
                logger.error(f"Inner exception processing notification {notification_id_str}: {e_inner}. Rolling back.")
                if hasattr(db_conn, 'rollback'): 
                    await db_conn.rollback()
                await message.nack(requeue=True) 
                return


    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON message: {e}. Body: {message.body.decode()[:500]}")
        await message.nack(requeue=False) # Discard malformed JSON
    except Exception as e: # Catch-all for other errors like Pydantic validation earlier or connection issues
        logger.error(f"Outer unexpected error processing message: {e}. Message will be NACKed (requeued by default or based on policy).")
        await message.nack(requeue=True) # Requeue for unknown errors, could be transient

async def main():
    logger.info("Notification worker starting...")
    # The consume_messages function in queue.py handles the connection and consumption loop.
    await queue.consume_messages(
        queue_name=settings.RABBITMQ_QUEUE_NAME,
        on_message_callback=process_notification_message
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Notification worker shutting down due to KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"Notification worker faced a critical error and is shutting down: {e}", exc_info=True)
