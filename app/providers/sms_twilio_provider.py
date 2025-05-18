import logging
import asyncio
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.config import settings # Assuming settings will be accessible here

logger = logging.getLogger(__name__)

def send_sms_sync(recipient_phone: str, message_body: str) -> bool:
    """
    Sends an SMS synchronously using Twilio.
    This function is intended to be run in a separate thread by an async caller.
    It prioritizes using MessagingServiceSid if available.
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.error("Twilio Account SID or Auth Token is not configured. Cannot send SMS.")
        return False

    # Check for either MessagingServiceSid or FromNumber
    if not settings.TWILIO_MESSAGING_SERVICE_SID and not settings.TWILIO_FROM_NUMBER:
        logger.error("Neither Twilio Messaging Service SID nor From Number is configured. Cannot send SMS.")
        return False

    if not recipient_phone or not message_body:
        logger.error("Recipient phone or message body is missing. Cannot send SMS.")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        send_params = {
            "body": message_body,
            "to": recipient_phone
        }

        if settings.TWILIO_MESSAGING_SERVICE_SID:
            send_params["messaging_service_sid"] = settings.TWILIO_MESSAGING_SERVICE_SID
            logger.info(f"Attempting to send Twilio SMS to {recipient_phone} using MessagingServiceSid: {settings.TWILIO_MESSAGING_SERVICE_SID}")
        elif settings.TWILIO_FROM_NUMBER:
            send_params["from_"] = settings.TWILIO_FROM_NUMBER
            logger.info(f"Attempting to send Twilio SMS to {recipient_phone} from number: {settings.TWILIO_FROM_NUMBER}")
        else:
            # This case should be caught by the earlier check, but as a safeguard
            logger.error("No valid sender (MessagingServiceSid or FromNumber) configured for Twilio.")
            return False
            
        message = client.messages.create(**send_params)
        
        if message.sid and message.status not in ['failed', 'undelivered']:
            logger.info(f"Twilio SMS successfully sent to {recipient_phone}. SID: {message.sid}, Status: {message.status}")
            return True
        else:
            logger.error(f"Failed to send Twilio SMS to {recipient_phone}. SID: {message.sid}, Status: {message.status}, Error: {message.error_message}")
            return False
            
    except TwilioRestException as e:
        logger.error(f"Twilio API error sending SMS to {recipient_phone}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending Twilio SMS to {recipient_phone}: {e}")
        
    return False

async def send_sms_async(recipient_phone: str, message_body: str) -> bool: # Renamed for consistency
    """
    Asynchronous wrapper for the synchronous Twilio send_sms_sync function.
    """
    return await asyncio.to_thread(send_sms_sync, recipient_phone, message_body)
