import logging
import asyncio
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

def send_ses_email_sync(
    recipient_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    sender_email: str = settings.EMAIL_SENDER # This must be a verified SES identity
) -> bool:
    """
    Sends an email synchronously using AWS SES (Simple Email Service v2).
    This function is intended to be run in a separate thread by an async caller.
    """
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        logger.error("AWS credentials (access key or secret key) are not configured. Cannot send SES email.")
        return False

    if not recipient_email or not subject or not text_body:
        logger.error("Recipient email, subject, or text body is missing. Cannot send SES email.")
        return False
    
    if not sender_email: # Should be set via settings.EMAIL_SENDER
        logger.error("Sender email (verified SES identity) is not configured. Cannot send SES email.")
        return False

    try:
        ses_client = boto3.client(
            "sesv2", # Using SES API v2
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME
        )

        email_content = {"Simple": {"Subject": {"Data": subject}, "Body": {}}}
        if text_body:
            email_content["Simple"]["Body"]["Text"] = {"Data": text_body}
        if html_body:
            email_content["Simple"]["Body"]["Html"] = {"Data": html_body}
        
        # If only HTML is provided, SES requires a Text part. If only Text, that's fine.
        # If both are provided, SES sends a multipart/alternative email.
        # If text_body is None but html_body is present, we should ideally generate a text version
        # or ensure text_body is always present. For now, assume text_body is primary.
        if not text_body and html_body: # Simple fallback if only HTML is given
             email_content["Simple"]["Body"]["Text"] = {"Data": "Please view this email in an HTML-compatible viewer."}


        logger.info(f"Attempting to send SES email from {sender_email} to {recipient_email} via region {settings.AWS_REGION_NAME}")

        response = ses_client.send_email(
            FromEmailAddress=sender_email,
            Destination={"ToAddresses": [recipient_email]},
            Content=email_content
            # ReplyToAddresses=[sender_email], # Optional
            # ConfigurationSetName='string' # Optional: For tracking, event publishing
        )
        
        message_id = response.get('MessageId')
        if message_id:
            logger.info(f"SES email successfully sent to {recipient_email}. MessageID: {message_id}")
            return True
        else:
            logger.error(f"Failed to send SES email to {recipient_email}. No MessageId in response: {response}")
            return False
            
    except (NoCredentialsError, PartialCredentialsError) as e:
        logger.error(f"AWS credentials error sending SES email to {recipient_email}: {e}")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        error_message = e.response.get("Error", {}).get("Message")
        logger.error(f"AWS SES API error sending email to {recipient_email}: {error_code} - {error_message}. Details: {e}")
        if error_code == "MessageRejected":
            logger.error("SES MessageRejected: This might be due to an unverified sender/receiver email in sandbox mode, or other SES sending policies.")
    except Exception as e:
        logger.error(f"Unexpected error sending SES email to {recipient_email}: {e}")
        
    return False

async def send_email_async(
    recipient_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    sender_email: str = settings.EMAIL_SENDER
) -> bool:
    """
    Asynchronous wrapper for the synchronous AWS SES send_email_sync function.
    """
    return await asyncio.to_thread(
        send_ses_email_sync,
        recipient_email,
        subject,
        text_body,
        html_body,
        sender_email
    )
