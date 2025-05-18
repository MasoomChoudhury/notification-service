import logging
import asyncio
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

from app.config import settings # Assuming settings will be accessible here

logger = logging.getLogger(__name__)

def send_sns_sms_sync(recipient_phone: str, message_body: str) -> bool:
    """
    Sends an SMS synchronously using AWS SNS.
    This function is intended to be run in a separate thread by an async caller.
    """
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        logger.error("AWS credentials (access key or secret key) are not configured. Cannot send SNS SMS.")
        return False

    if not recipient_phone or not message_body:
        logger.error("Recipient phone or message body is missing. Cannot send SNS SMS.")
        return False

    try:
        # Ensure region_name is explicitly passed, otherwise Boto3 might look in ~/.aws/config
        sns_client = boto3.client(
            "sns",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME  # Ensure this is set and valid
        )

        message_attributes = {
            'AWS.SNS.SMS.SMSType': {
                'DataType': 'String',
                'StringValue': settings.SNS_SMS_TYPE
            }
        }
        if settings.SNS_SENDER_ID:
            message_attributes['AWS.SNS.SMS.SenderID'] = {
                'DataType': 'String',
                'StringValue': settings.SNS_SENDER_ID
            }
        
        logger.info(f"Attempting to send SNS SMS to {recipient_phone} via region {settings.AWS_REGION_NAME}")
        if settings.SNS_SENDER_ID:
            logger.info(f"Using SNS Sender ID: {settings.SNS_SENDER_ID}")
        logger.info(f"Using SNS SMS Type: {settings.SNS_SMS_TYPE}")

        response = sns_client.publish(
            PhoneNumber=recipient_phone, # Must be E.164 format
            Message=message_body,
            MessageAttributes=message_attributes
        )
        
        message_id = response.get('MessageId')
        if message_id:
            logger.info(f"SNS SMS successfully published to {recipient_phone}. MessageID: {message_id}")
            return True
        else:
            logger.error(f"Failed to send SNS SMS to {recipient_phone}. No MessageId in response: {response}")
            return False
            
    except (NoCredentialsError, PartialCredentialsError) as e:
        logger.error(f"AWS credentials error sending SNS SMS to {recipient_phone}: {e}")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        error_message = e.response.get("Error", {}).get("Message")
        logger.error(f"AWS SNS API error sending SMS to {recipient_phone}: {error_code} - {error_message}. Details: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending SNS SMS to {recipient_phone}: {e}")
        
    return False

async def send_sms_async(recipient_phone: str, message_body: str) -> bool: # Renamed for consistency
    """
    Asynchronous wrapper for the synchronous AWS SNS send_sns_sms_sync function.
    """
    return await asyncio.to_thread(send_sns_sms_sync, recipient_phone, message_body)
