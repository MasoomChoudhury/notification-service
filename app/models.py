from enum import Enum
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime

from pydantic import BaseModel, Field, EmailStr, validator
# Consider adding phonenumbers for validation if recipient_phone is critical
# from pydantic_extra_types.phone_numbers import PhoneNumber # If using pydantic-extra-types

class ChannelEnum(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    IN_APP = "IN_APP"
    PUSH_ANDROID = "PUSH_ANDROID" # Added for Android Push

class SmsProviderEnum(str, Enum):
    TWILIO = "TWILIO"
    AWS_SNS = "AWS_SNS"
    TEXTBEE = "TEXTBEE" # Replaced HTTP_SMS with TEXTBEE

class NotificationStatusEnum(str, Enum):
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED" # For notifications to be sent at a future time
    PROCESSING_STUB = "PROCESSING_STUB" # Picked up by the stub worker
    SENT = "SENT" # Successfully sent by a real worker
    FAILED = "FAILED" # Failed to send after retries or critical error
    # More granular statuses like DELIVERED, OPENED could be added later if needed

class NotificationRequest(BaseModel):
    channel: ChannelEnum
    sms_provider: Optional[SmsProviderEnum] = None 
    recipient_email: Optional[EmailStr] = None
    recipient_phone: Optional[str] = None 
    user_id: Optional[str] = None # Used for IN_APP and PUSH_ANDROID
    subject: Optional[str] = None # Primarily for EMAIL
    message_body: str = Field(..., min_length=1) # Main content for SMS, text part of Email, push body
    message_html: Optional[str] = None # For EMAIL channel primarily
    
    # Push Notification specific fields
    push_title: Optional[str] = None
    # push_body is covered by message_body
    push_data: Optional[Dict[str, Any]] = None # Custom data payload for push

    send_at: Optional[datetime] = None 
    metadata: Optional[Dict[str, Any]] = None

    @validator('recipient_email', always=True)
    def check_email_for_email_channel(cls, v, values):
        if values.get('channel') == ChannelEnum.EMAIL and not v:
            raise ValueError("recipient_email is required for EMAIL channel")
        return v

    @validator('recipient_phone', always=True)
    def check_phone_for_sms_channel(cls, v, values):
        if values.get('channel') == ChannelEnum.SMS and not v:
            raise ValueError("recipient_phone is required for SMS channel")
        # Add more sophisticated phone number validation here if needed
        # e.g., using the phonenumbers library
        return v
    
    @validator('user_id', always=True)
    def check_user_id_for_relevant_channels(cls, v, values): # Renamed and updated
        channel = values.get('channel')
        if channel == ChannelEnum.IN_APP and not v:
            raise ValueError("user_id is required for IN_APP channel")
        if channel == ChannelEnum.PUSH_ANDROID and not v:
            raise ValueError("user_id is required for PUSH_ANDROID channel")
        return v

    @validator('subject', always=True)
    def check_subject_for_email_channel(cls, v, values):
        if values.get('channel') == ChannelEnum.EMAIL and not v:
            raise ValueError("subject is required for EMAIL channel")
        return v

    @validator('sms_provider', always=True)
    def check_sms_provider_for_sms_channel(cls, v, values):
        if values.get('channel') == ChannelEnum.SMS and not v:
            raise ValueError("sms_provider is required for SMS channel")
        return v

    # Removed duplicated user_id validator, merged logic into check_user_id_for_relevant_channels

    @validator('push_title', always=True)
    def check_push_title_for_push_channel(cls, v, values):
        if values.get('channel') == ChannelEnum.PUSH_ANDROID and not v:
            # Title can be optional for some push types, but let's require for simplicity now
            # Or, if message_body can serve as body, title might be more important.
            # For now, let's not make it strictly required, but it's good to have.
            pass # Making it optional for now, can be made required if needed
        return v

    # message_body will serve as push_body, no separate validator needed if already required.

class NotificationResponse(BaseModel):
    message: str
    notificationId: UUID

class NotificationDB(NotificationRequest):
    id: UUID = Field(default_factory=uuid4)
    status: NotificationStatusEnum = NotificationStatusEnum.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    retry_count: int = 0

    class Config:
        orm_mode = True # For compatibility if using with an ORM later
        # For Pydantic V2, orm_mode is now from_attributes = True
        # from_attributes = True 

# Example of a model for the worker to consume from RabbitMQ
class NotificationMessage(NotificationDB):
    # This can be the same as NotificationDB or a subset/superset
    # depending on what the worker needs.
    # For now, assume it's the same as what's stored in DB initially.
    pass

# Models for Push Subscriptions (SNS specific for Android)
class SnsPushSubscriptionBase(BaseModel):
    user_id: str = Field(..., description="The user ID this subscription belongs to.")
    fcm_token: str = Field(..., description="The FCM registration token from the Android device.")

class SnsPushSubscriptionCreate(SnsPushSubscriptionBase):
    pass

class SnsPushSubscriptionDB(SnsPushSubscriptionBase):
    id: UUID = Field(default_factory=uuid4, description="Unique ID for the subscription entry.")
    endpoint_arn: str = Field(..., description="The AWS SNS Endpoint ARN for this subscription.")
    platform: str = "ANDROID_SNS" # Could be an enum if supporting more push platforms via SNS
    is_enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow) # When token was last updated or endpoint re-created

    class Config:
        orm_mode = True
        # from_attributes = True # For Pydantic V2
