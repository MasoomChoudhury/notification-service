import logging
from app.models import SmsProviderEnum, NotificationMessage
from app.config import settings

# Import provider-specific send functions
from app.providers import sms_twilio_provider
from app.providers import sms_aws_sns_provider
from app.providers import sms_textbee_provider # Changed from sms_http_provider

logger = logging.getLogger(__name__)

async def send_sms_via_provider(
    provider: SmsProviderEnum,
    recipient_phone: str,
    message_body: str,
    notification_id_str: str # For logging context
) -> bool:
    """
    Dispatches SMS sending to the specified provider.
    """
    logger.info(f"Dispatching SMS for notification ID {notification_id_str} via provider: {provider.value}")

    if provider == SmsProviderEnum.TWILIO:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or \
           (not settings.TWILIO_MESSAGING_SERVICE_SID and not settings.TWILIO_FROM_NUMBER):
            logger.error(f"Twilio credentials not fully configured for notification ID {notification_id_str}. Cannot send SMS via Twilio.")
            return False
        return await sms_twilio_provider.send_sms_async(recipient_phone, message_body)
    
    elif provider == SmsProviderEnum.AWS_SNS:
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            logger.error(f"AWS SNS credentials not configured for notification ID {notification_id_str}. Cannot send SMS via AWS SNS.")
            return False
        return await sms_aws_sns_provider.send_sms_async(recipient_phone, message_body)
        
    elif provider == SmsProviderEnum.TEXTBEE: # Changed from HTTP_SMS to TEXTBEE
        if not settings.TEXTBEE_API_KEY or not settings.TEXTBEE_DEVICE_ID:
            logger.error(f"Textbee API Key or Device ID not configured for notification ID {notification_id_str}. Cannot send SMS via Textbee.")
            return False
        return await sms_textbee_provider.send_sms_async(recipient_phone, message_body) # Changed provider
        
    else:
        logger.error(f"Unknown SMS provider: {provider.value} for notification ID {notification_id_str}")
        return False

# This wrapper can be called by the worker.
# It extracts necessary info from the NotificationMessage.
async def send_sms_message(notification_message: NotificationMessage) -> bool:
    """
    Main function called by the worker to send an SMS based on the
    provider specified in the notification_message.
    """
    if not notification_message.sms_provider:
        logger.error(f"SMS provider not specified for notification ID {notification_message.id}. Cannot send SMS.")
        return False
    
    if not notification_message.recipient_phone or not notification_message.message_body:
        logger.error(f"Recipient phone or message body missing for SMS notification ID {notification_message.id}.")
        return False

    return await send_sms_via_provider(
        provider=notification_message.sms_provider,
        recipient_phone=notification_message.recipient_phone,
        message_body=notification_message.message_body,
        notification_id_str=str(notification_message.id)
    )
