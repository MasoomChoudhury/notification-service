import sqlite3
import aiosqlite
import json
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime # Added missing import

from app.config import settings
from app import models # Changed import to use models namespace

logger = logging.getLogger(__name__)

DATABASE_URL = settings.DATABASE_URL.split("///")[-1] # Get the file path part

@asynccontextmanager
async def get_db_connection():
    """Provides an asynchronous database connection."""
    conn = None
    try:
        logger.info(f"Attempting to connect to database: {DATABASE_URL}")
        conn = await aiosqlite.connect(DATABASE_URL)
        # Enable row factory to access columns by name
        conn.row_factory = aiosqlite.Row
        logger.info(f"Successfully connected to database: {DATABASE_URL}")
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            await conn.close()
            logger.info(f"Database connection closed: {DATABASE_URL}")

async def create_tables(conn: Optional[aiosqlite.Connection] = None):
    """Creates database tables if they don't exist."""
    should_close_conn = False
    if conn is None:
        conn = await aiosqlite.connect(DATABASE_URL)
        conn.row_factory = aiosqlite.Row
        should_close_conn = True

    try:
        async with conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            PRAGMA busy_timeout = 5000;
            PRAGMA synchronous = NORMAL;

            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                channel TEXT NOT NULL CHECK (channel IN ('EMAIL', 'SMS', 'IN_APP')),
                recipient_email TEXT,
            recipient_phone TEXT,
            user_id TEXT,
            subject TEXT,
            message_body TEXT NOT NULL,
            message_html TEXT,
            send_at TIMESTAMP,
            metadata TEXT, -- Store as JSON string
            sms_provider TEXT, -- Added for selecting SMS provider
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            retry_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
            CREATE INDEX IF NOT EXISTS idx_notifications_send_at ON notifications(send_at);
            CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

            CREATE TRIGGER IF NOT EXISTS update_notifications_updated_at
            AFTER UPDATE ON notifications
            FOR EACH ROW
            BEGIN
                UPDATE notifications SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;

            CREATE TABLE IF NOT EXISTS android_sns_push_subscriptions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                fcm_token TEXT NOT NULL,
                endpoint_arn TEXT NOT NULL UNIQUE, -- Endpoint ARN should be unique
                platform TEXT NOT NULL DEFAULT 'ANDROID_SNS',
                is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_android_sns_push_subscriptions_user_id ON android_sns_push_subscriptions(user_id);
            CREATE INDEX IF NOT EXISTS idx_android_sns_push_subscriptions_fcm_token ON android_sns_push_subscriptions(fcm_token);
            CREATE INDEX IF NOT EXISTS idx_android_sns_push_subscriptions_is_enabled ON android_sns_push_subscriptions(is_enabled);

            CREATE TRIGGER IF NOT EXISTS update_android_sns_push_subscriptions_updated_at
            AFTER UPDATE ON android_sns_push_subscriptions
            FOR EACH ROW
            BEGIN
                UPDATE android_sns_push_subscriptions SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;
            """
            # Optional users table (DDL commented out for now as per plan)
            # """
            # CREATE TABLE IF NOT EXISTS users (
            #     id TEXT PRIMARY KEY,
            #     username TEXT UNIQUE NOT NULL,
            #     email TEXT UNIQUE,
            #     phone_number TEXT UNIQUE,
            #     hashed_password TEXT NOT NULL,
            #     created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            #     updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            # );
            # CREATE TRIGGER IF NOT EXISTS update_users_updated_at
            # AFTER UPDATE ON users
            # FOR EACH ROW
            # BEGIN
            #     UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            # END;
            # """
        ):
            await conn.commit()
        logger.info("Database tables checked/created successfully, PRAGMAs set.")
    except sqlite3.Error as e:
        logger.error(f"Error creating database tables: {e}")
        raise
    finally:
        if should_close_conn and conn:
            await conn.close()


async def insert_notification(conn: aiosqlite.Connection, notification: models.NotificationDB) -> UUID:
    """Inserts a new notification into the database."""
    sql = """
        INSERT INTO notifications (
            id, channel, recipient_email, recipient_phone, user_id, subject,
            message_body, message_html, metadata, sms_provider, status, created_at, updated_at, send_at, retry_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    # Determine status based on send_at
    current_status = notification.status
    if notification.send_at and notification.send_at > notification.created_at:
        current_status = models.NotificationStatusEnum.SCHEDULED
    
    # Ensure metadata is a JSON string
    metadata_json = json.dumps(notification.metadata) if notification.metadata is not None else None

    try:
        await conn.execute(
            sql,
            (
                str(notification.id), notification.channel.value, notification.recipient_email,
                notification.recipient_phone, notification.user_id, notification.subject,
                notification.message_body, notification.message_html, metadata_json,
                notification.sms_provider.value if notification.sms_provider else None, # Add sms_provider
                current_status.value, notification.created_at, notification.updated_at,
                notification.send_at, notification.retry_count,
            ),
        )
        # await conn.commit() # Commit will be handled by the calling transaction
        logger.info(f"Notification {notification.id} prepared for insertion with status {current_status.value}.")
        return notification.id
    except sqlite3.Error as e:
        logger.error(f"Error inserting notification {notification.id}: {e}")
        raise

async def update_notification_status(conn: aiosqlite.Connection, notification_id: UUID, status: models.NotificationStatusEnum, retry_count: Optional[int] = None) -> bool:
    """Updates the status and optionally retry_count of a notification."""
    fields_to_update = {"status": status.value, "updated_at": "CURRENT_TIMESTAMP"}
    params = [status.value, str(notification_id)]

    if retry_count is not None:
        fields_to_update["retry_count"] = retry_count
        sql = "UPDATE notifications SET status = ?, retry_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        params = [status.value, retry_count, str(notification_id)]
    else:
        sql = "UPDATE notifications SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        params = [status.value, str(notification_id)]
    
    try:
        cursor = await conn.execute(sql, tuple(params))
        # await conn.commit() # Commit will be handled by the calling transaction
        if cursor.rowcount > 0:
            logger.info(f"Notification {notification_id} status updated to {status.value}" + (f" and retry_count to {retry_count}" if retry_count is not None else ""))
            return True
        logger.warning(f"Notification {notification_id} not found for status update.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error updating notification {notification_id} status: {e}")
        raise

async def get_notification_by_id(conn: aiosqlite.Connection, notification_id: UUID) -> Optional[models.NotificationMessage]:
    """Retrieves a notification by its ID."""
    sql = "SELECT * FROM notifications WHERE id = ?"
    try:
        async with conn.execute(sql, (str(notification_id),)) as cursor:
            row = await cursor.fetchone()
            if row:
                # Convert row to NotificationMessage model
                row_dict = dict(row)
                if row_dict.get('metadata'):
                    row_dict['metadata'] = json.loads(row_dict['metadata'])
                return models.NotificationMessage(**row_dict)
            return None
    except sqlite3.Error as e:
        logger.error(f"Error retrieving notification {notification_id}: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding metadata for notification {notification_id}: {e}")
        # Potentially return the notification with metadata as None or raise a specific error
        return None


# Example: Function to fetch scheduled notifications (for a scheduler component, not used in this phase)
async def get_scheduled_notifications_to_send(conn: aiosqlite.Connection, limit: int = 100) -> List[models.NotificationMessage]:
    """Retrieves scheduled notifications that are due to be sent."""
    sql = """
        SELECT * FROM notifications
        WHERE status = ? AND send_at <= CURRENT_TIMESTAMP
        ORDER BY send_at ASC
        LIMIT ?
    """
    notifications = []
    try:
        async with conn.execute(sql, (models.NotificationStatusEnum.SCHEDULED.value, limit)) as cursor:
            async for row in cursor:
                row_dict = dict(row)
                if row_dict.get('metadata'):
                    row_dict['metadata'] = json.loads(row_dict['metadata'])
                notifications.append(models.NotificationMessage(**row_dict))
        return notifications
    except sqlite3.Error as e:
        logger.error(f"Error retrieving scheduled notifications: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding metadata for a scheduled notification: {e}")
        # Decide how to handle this, e.g., skip the problematic record or raise
        return []

# --- Functions for SNS Push Subscriptions ---

async def add_sns_push_subscription(conn: aiosqlite.Connection, subscription: models.SnsPushSubscriptionDB) -> models.SnsPushSubscriptionDB:
    """Adds or updates an SNS push subscription."""
    # Check if a subscription with this fcm_token already exists for the user_id
    # If so, update its endpoint_arn and updated_at. If not, insert new.
    # SNS create_platform_endpoint is idempotent for a given token on a platform application,
    # but it might return the same or a new ARN, or an error if attributes change.
    # For simplicity, we'll try to insert, and on unique constraint violation for endpoint_arn,
    # it means something is wrong or needs more complex handling (e.g. token belongs to different user).
    # A better approach might be to query by fcm_token first.

    sql_select = "SELECT * FROM android_sns_push_subscriptions WHERE user_id = ? AND fcm_token = ?"
    async with conn.execute(sql_select, (subscription.user_id, subscription.fcm_token)) as cursor:
        existing = await cursor.fetchone()

    now = datetime.utcnow()
    if existing:
        # Token already exists for this user. Update endpoint_arn if different, and updated_at.
        if existing["endpoint_arn"] != subscription.endpoint_arn:
            logger.info(f"FCM token for user {subscription.user_id} has a new Endpoint ARN. Updating.")
        sql_update = """
            UPDATE android_sns_push_subscriptions 
            SET endpoint_arn = ?, updated_at = ?, is_enabled = TRUE
            WHERE id = ?
        """
        await conn.execute(sql_update, (subscription.endpoint_arn, now, existing["id"]))
        subscription.id = existing["id"] # Keep original ID
        subscription.created_at = existing["created_at"] # Keep original creation time
        subscription.updated_at = now
        logger.info(f"Updated SNS push subscription for user {subscription.user_id}, fcm_token ending ...{subscription.fcm_token[-10:]}")
    else:
        # New subscription for this user/fcm_token combination
        sql_insert = """
            INSERT INTO android_sns_push_subscriptions 
                (id, user_id, fcm_token, endpoint_arn, platform, is_enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        subscription.created_at = now
        subscription.updated_at = now
        await conn.execute(sql_insert, (
            str(subscription.id), subscription.user_id, subscription.fcm_token, 
            subscription.endpoint_arn, subscription.platform, subscription.is_enabled,
            subscription.created_at, subscription.updated_at
        ))
        logger.info(f"Added new SNS push subscription for user {subscription.user_id}, fcm_token ending ...{subscription.fcm_token[-10:]}")
    
    # await conn.commit() # Handled by calling transaction
    return subscription

async def get_sns_push_subscriptions_by_user_id(conn: aiosqlite.Connection, user_id: str) -> List[models.SnsPushSubscriptionDB]:
    """Retrieves all active SNS push subscriptions for a user."""
    sql = "SELECT * FROM android_sns_push_subscriptions WHERE user_id = ? AND is_enabled = TRUE"
    subscriptions = []
    async with conn.execute(sql, (user_id,)) as cursor:
        async for row in cursor:
            subscriptions.append(models.SnsPushSubscriptionDB(**dict(row)))
    return subscriptions

async def delete_sns_push_subscription_by_endpoint_arn(conn: aiosqlite.Connection, endpoint_arn: str) -> bool:
    """Deletes an SNS push subscription by its Endpoint ARN."""
    sql = "DELETE FROM android_sns_push_subscriptions WHERE endpoint_arn = ?"
    cursor = await conn.execute(sql, (endpoint_arn,))
    # await conn.commit() # Handled by calling transaction
    if cursor.rowcount > 0:
        logger.info(f"Deleted SNS push subscription with Endpoint ARN: {endpoint_arn}")
        return True
    logger.warning(f"SNS push subscription with Endpoint ARN: {endpoint_arn} not found for deletion.")
    return False

async def disable_sns_push_subscription_by_endpoint_arn(conn: aiosqlite.Connection, endpoint_arn: str) -> bool:
    """Marks an SNS push subscription as disabled."""
    sql = "UPDATE android_sns_push_subscriptions SET is_enabled = FALSE, updated_at = CURRENT_TIMESTAMP WHERE endpoint_arn = ?"
    cursor = await conn.execute(sql, (endpoint_arn,))
    # await conn.commit() # Handled by calling transaction
    if cursor.rowcount > 0:
        logger.info(f"Disabled SNS push subscription with Endpoint ARN: {endpoint_arn}")
        return True
    return False
