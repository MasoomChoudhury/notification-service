import logging
import asyncio
import httpx  # Using httpx for async HTTP requests

from app.config import settings

logger = logging.getLogger(__name__)

async def send_sms_async(recipient_phone: str, message_body: str) -> bool:
    """
    Sends an SMS using the Textbee provider.
    API Docs provided by user.
    """
    if not settings.TEXTBEE_API_KEY or not settings.TEXTBEE_DEVICE_ID:
        logger.error("Textbee API Key or Device ID is not configured. Cannot send Textbee SMS.")
        return False

    if not recipient_phone or not message_body:
        logger.error("Recipient phone or message body is missing for Textbee SMS.")
        return False

    # Construct the API URL using the device ID from settings
    api_url = f"https://api.textbee.dev/api/v1/gateway/devices/{settings.TEXTBEE_DEVICE_ID}/send-sms"
    api_key = settings.TEXTBEE_API_KEY

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }

    # Textbee expects recipients as an array
    payload = {
        "recipients": [recipient_phone],
        "message": message_body,
    }

    try:
        logger.info(f"Attempting to send Textbee SMS to {recipient_phone} via {api_url}")
        logger.debug(f"Textbee payload: {payload}")
        logger.debug(f"Textbee headers: {headers}")

        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, json=payload)
            
            logger.debug(f"Textbee raw response status: {response.status_code}")
            logger.debug(f"Textbee raw response content: {response.text}")

            # Assuming 2xx indicates success for Textbee as no specific success/error response structure was provided
            if 200 <= response.status_code < 300:
                logger.info(f"Textbee SMS successfully sent/queued to {recipient_phone}. Status: {response.status_code}")
                # If Textbee provides a message ID or more details in response, parse here
                # For now, just log the text if any
                if response.text:
                    logger.info(f"Textbee response body: {response.text}")
                return True
            else:
                logger.error(f"Failed to send Textbee SMS to {recipient_phone}. Status: {response.status_code}, Response: {response.text}")
                return False

    except httpx.HTTPStatusError as e:
        error_detail = e.response.text
        try:
            error_json = e.response.json()
            error_detail = error_json.get("message") or error_detail # Common key for error messages
        except ValueError:
            pass 
        logger.error(f"HTTP error sending Textbee SMS to {recipient_phone}: {e.response.status_code} - {error_detail}")
    except httpx.RequestError as e:
        logger.error(f"Request error sending Textbee SMS to {recipient_phone}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending Textbee SMS to {recipient_phone}: {e}")
        
    return False
