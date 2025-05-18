import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Callable, Awaitable, Optional

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractChannel, AbstractQueue, AbstractIncomingMessage

from app.config import settings
from app.models import NotificationMessage # For deserializing messages if needed by callback

logger = logging.getLogger(__name__)

RABBITMQ_URL = settings.RABBITMQ_URL
RABBITMQ_QUEUE_NAME = settings.RABBITMQ_QUEUE_NAME

@asynccontextmanager
async def get_rabbitmq_connection() -> AbstractRobustConnection:
    """Provides a robust RabbitMQ connection."""
    connection = None
    try:
        logger.info(f"Attempting to connect to RabbitMQ: {RABBITMQ_URL}")
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        logger.info("Successfully connected to RabbitMQ.")
        yield connection
    except aio_pika.exceptions.AMQPConnectionError as e:
        logger.error(f"RabbitMQ connection error: {e}")
        raise
    finally:
        if connection and not connection.is_closed:
            await connection.close()
            logger.info("RabbitMQ connection closed.")

@asynccontextmanager
async def get_rabbitmq_channel(connection: AbstractRobustConnection) -> AbstractChannel:
    """Provides a RabbitMQ channel from a given connection."""
    channel = None
    try:
        channel = await connection.channel()
        logger.info("RabbitMQ channel obtained.")
        yield channel
    except aio_pika.exceptions.AMQPError as e:
        logger.error(f"Error obtaining RabbitMQ channel: {e}")
        raise
    finally:
        if channel and not channel.is_closed:
            await channel.close()
            logger.info("RabbitMQ channel closed.")

async def declare_queue(channel: AbstractChannel, queue_name: str) -> AbstractQueue:
    """Declares a durable queue."""
    try:
        queue = await channel.declare_queue(
            queue_name,
            durable=True # Ensure queue survives broker restart
        )
        logger.info(f"Queue '{queue_name}' declared successfully (durable).")
        return queue
    except aio_pika.exceptions.AMQPError as e:
        logger.error(f"Error declaring queue '{queue_name}': {e}")
        raise

async def publish_message(channel: AbstractChannel, queue_name: str, message_body: Dict[str, Any]):
    """Publishes a persistent message to the specified queue (via default exchange)."""
    try:
        message_json = json.dumps(message_body, default=str) # Use default=str for datetime/UUID
        message = aio_pika.Message(
            body=message_json.encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT # Ensure message survives broker restart
        )
        await channel.default_exchange.publish(
            message,
            routing_key=queue_name
        )
        logger.info(f"Message published to queue '{queue_name}'. Body: {message_json[:200]}...") # Log snippet
    except TypeError as e:
        logger.error(f"Error serializing message to JSON for queue '{queue_name}': {e}. Body: {message_body}")
        raise
    except aio_pika.exceptions.AMQPError as e:
        logger.error(f"Error publishing message to queue '{queue_name}': {e}")
        raise

async def consume_messages(
    queue_name: str,
    on_message_callback: Callable[[AbstractIncomingMessage], Awaitable[None]]
):
    """
    Connects to RabbitMQ, declares a queue, and consumes messages indefinitely.
    The on_message_callback is responsible for processing and acknowledging the message.
    """
    while True: # Keep trying to connect and consume
        try:
            async with get_rabbitmq_connection() as connection:
                async with get_rabbitmq_channel(connection) as channel:
                    await channel.set_qos(prefetch_count=1) # Process one message at a time per consumer
                    queue = await declare_queue(channel, queue_name)
                    logger.info(f"Worker started consuming from queue: '{queue_name}'")
                    
                    async with queue.iterator() as queue_iter:
                        async for message in queue_iter:
                            try:
                                await on_message_callback(message)
                            except Exception as e:
                                logger.error(f"Error processing message from '{queue_name}': {e}. Message body (raw): {message.body[:200]}")
                                # Decide on nack strategy here if needed, e.g., nack without requeue
                                # await message.nack(requeue=False) # Example: move to DLX or discard
                                # For now, if callback errors, message might be redelivered if not acked/nacked by callback
                                # The callback (process_notification_message in worker.py) should handle ack/nack.

        except aio_pika.exceptions.AMQPConnectionError as e:
            logger.error(f"RabbitMQ connection error during consumption: {e}. Retrying in 10 seconds...")
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            logger.info("Consumption task cancelled.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in consumer loop for '{queue_name}': {e}. Retrying in 10 seconds...")
            await asyncio.sleep(10)

# Example usage for a worker (simplified):
# async def my_message_handler(message: AbstractIncomingMessage):
#     async with message.process(): # This will ack the message upon successful completion of the block
#         print(f"Received message: {message.body.decode()}")
#         # If an error occurs here, the message will be nack'd and requeued by default
#
# if __name__ == "__main__":
#     loop = asyncio.get_event_loop()
#     try:
#         loop.create_task(consume_messages("my_test_queue", my_message_handler))
#         loop.run_forever()
#     except KeyboardInterrupt:
#         print("Worker shutting down...")
#     finally:
#         loop.close()
