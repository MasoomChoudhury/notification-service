import os
from typing import Optional # Added import for Optional
from pydantic_settings import BaseSettings, SettingsConfigDict # Updated import
from pydantic import Field

class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    RABBITMQ_URL: str = Field(..., env="RABBITMQ_URL")
    API_BASE_PATH: str = Field("/notification-service", env="API_BASE_PATH")
    RABBITMQ_QUEUE_NAME: str = "notification_tasks"

    # General Email Sender (used by SES, ensure this is a verified SES identity)
    EMAIL_SENDER: str = Field("notifications@example.com", env="EMAIL_SENDER") 
    # SMTP_HOST and SMTP_PORT removed as we are switching to SES

    # AWS Settings (used for SNS and SES)
    AWS_ACCESS_KEY_ID: Optional[str] = Field(None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(None, env="AWS_SECRET_ACCESS_KEY")
    AWS_REGION_NAME: str = Field("us-east-1", env="AWS_REGION_NAME")
    SNS_SENDER_ID: Optional[str] = Field(None, env="SNS_SENDER_ID") # For SMS
    SNS_SMS_TYPE: str = Field("Transactional", env="SNS_SMS_TYPE") # For SMS
    SNS_PLATFORM_APPLICATION_ARN_ANDROID: Optional[str] = Field(None, env="SNS_PLATFORM_APPLICATION_ARN_ANDROID") # For Push

    # Twilio Settings (re-added)
    TWILIO_ACCOUNT_SID: Optional[str] = Field(None, env="TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(None, env="TWILIO_AUTH_TOKEN")
    TWILIO_MESSAGING_SERVICE_SID: Optional[str] = Field(None, env="TWILIO_MESSAGING_SERVICE_SID")
    TWILIO_FROM_NUMBER: Optional[str] = Field(None, env="TWILIO_FROM_NUMBER")

    # Textbee Settings
    TEXTBEE_API_KEY: Optional[str] = Field(None, env="TEXTBEE_API_KEY")
    TEXTBEE_DEVICE_ID: Optional[str] = Field(None, env="TEXTBEE_DEVICE_ID")

    # For Pydantic V2, configuration is done via model_config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra='ignore' # Allow extra env vars without failing
    )

settings = Settings()

# Example of how to load .env for local non-Docker runs if needed:
# from dotenv import load_dotenv
# load_dotenv()
# settings = Settings()

# You can access settings like:
# from app.config import settings
# db_url = settings.DATABASE_URL
