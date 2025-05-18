import logging
import asyncio
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.config import settings

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
            logger.info(f"Attempting to send SMS to {recipient_phone} using MessagingServiceSid: {settings.TWILIO_MESSAGING_SERVICE_SID}")
        elif settings.TWILIO_FROM_NUMBER: # Fallback if MessagingServiceSid is not set
            send_params["from_"] = settings.TWILIO_FROM_NUMBER
            logger.info(f"Attempting to send SMS to {recipient_phone} from number: {settings.TWILIO_FROM_NUMBER}")
        else:
            # This case should ideally be caught by the initial check, but as a safeguard:
            logger.error("No valid sender (MessagingServiceSid or FromNumber) configured for Twilio.")
            return False
            
        message = client.messages.create(**send_params)
        
        if message.sid and message.status not in ['failed', 'undelivered']:
            logger.info(f"SMS successfully sent to {recipient_phone}. SID: {message.sid}, Status: {message.status}")
            return True
        else:
            logger.error(f"Failed to send SMS to {recipient_phone}. SID: {message.sid}, Status: {message.status}, Error: {message.error_message}")
            return False
            
    except TwilioRestException as e:
        logger.error(f"Twilio API error sending SMS to {recipient_phone}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending SMS to {recipient_phone}: {e}")
        
    return False

async def send_sms_async_wrapper(recipient_phone: str, message_body: str) -> bool:
    """
    Asynchronous wrapper for the synchronous Twilio send_sms_sync function.
    """
    return await asyncio.to_thread(send_sms_sync, recipient_phone, message_body)

# Example usage (can be run directly for testing this module if .env is set up)
# if __name__ == "__main__":
#     async def test_send_sms():
#         # Ensure .env file has TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
#         # and a valid TWILIO_TEST_TO_NUMBER for testing.
#         test_to_number = os.getenv("TWILIO_TEST_TO_NUMBER")
#         if not test_to_number:
#             print("Please set TWILIO_TEST_TO_NUMBER environment variable for testing.")
#             return

#         if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM_NUMBER]):
#             print("Twilio credentials not found in settings. Ensure .env is loaded or env vars are set.")
#             return

#         success = await send_sms_async_wrapper(
#             recipient_phone=test_to_number, # Use a verified test number or your own
#             message_body="Hello from Notification Service (Twilio Test via Python!)"
#         )
#         if success:
#             print(f"Test SMS sent successfully to {test_to_number} (check Twilio logs).")
#         else:
#             print(f"Failed to send test SMS to {test_to_number}.")

#     # Load .env for direct script execution if needed
#     from dotenv import load_dotenv
#     load_dotenv()
#     # Re-initialize settings if .env was just loaded
#     settings = Settings() # This would require Settings class to be defined or imported here

#     asyncio.run(test_send_sms())
