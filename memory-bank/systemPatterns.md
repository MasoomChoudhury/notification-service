# System Patterns

## System Architecture
-   **Microservice Architecture:** The notification service is a standalone microservice.
-   **Containerized Deployment:** The application and its dependencies (RabbitMQ) will be containerized using Docker and orchestrated with Docker Compose for local development and potentially production.
-   **Asynchronous Processing:** Utilizes a message queue (RabbitMQ) to decouple notification submission from actual sending, improving API responsiveness and system resilience.
-   **Database:** SQLite is used for persistent storage of notification status and details, configured for robustness (WAL mode, busy_timeout).
-   **API-Driven:** Exposes a RESTful API (FastAPI) for other services to interact with.

## Key Technical Decisions
-   **Language/Framework:** Python with FastAPI for its asynchronous capabilities, performance, and ease of use for building APIs.
-   **Database:** SQLite for simplicity in this phase, with `aiosqlite` for async access. Robust PRAGMA settings are prioritized.
-   **Message Queue:** RabbitMQ for reliable message queuing and worker decoupling. `rabbitmq:3-management` image for built-in UI.
-   **Containerization:** Docker for packaging the application and its dependencies. Docker Compose for defining and running multi-container applications.
-   **Email Service Integration (Future):** AWS SES (via API calls).
-   **SMS Service Integration (Future):** Twilio (via API calls).

## Design Patterns in Use
-   **Producer-Consumer:** The API acts as a producer, publishing notification tasks to RabbitMQ. Workers act as consumers, processing these tasks.
-   **Repository Pattern (Conceptual):** Database interactions will be encapsulated in a dedicated module (`app/database.py`), abstracting data access logic.
-   **Dependency Injection (FastAPI):** FastAPI's dependency injection will be used for managing resources like database connections and queue connections within request handlers if applicable.
-   **Lifespan Events (FastAPI):** Used for managing resources like database and queue connections during application startup and shutdown.
-   **Outbox Pattern (Conceptual for DB & MQ):** The requirement to atomically insert into DB and publish to MQ resembles the outbox pattern's goal of ensuring consistency between local state changes and message publishing. This will be achieved through careful transaction management and error handling.

## Component Relationships
```mermaid
graph TD
    Client[External Client/Service] -- HTTP POST --> API[FastAPI App: /notification-service/notifications]
    API -- Writes to --> DB[(SQLite: notifications table)]
    API -- Publishes to --> MQ[RabbitMQ: notification_tasks queue]
    Worker[Python Worker] -- Consumes from --> MQ
    Worker -- Updates --> DB
    Worker -- HTTP POST (Future) --> SES[AWS SES]
    Worker -- HTTP POST (Future) --> Twilio[Twilio]

    subgraph DockerHost [Docker Host]
        direction LR
        subgraph AppContainer [app_service (Docker Container)]
            direction TB
            API
        end
        subgraph MQContainer [rabbitmq_service (Docker Container)]
            direction TB
            MQ
        end
        subgraph WorkerContainer [app_service (Worker Process)]
             direction TB
             Worker
        end
        AppContainer -- TCP --> MQContainer
        WorkerContainer -- TCP --> MQContainer
        AppContainer -- Mounts Volume --> HostDBData[./db_data]
        MQContainer -- Mounts Volume --> HostMQData[./rabbitmq_data]
    end
```

## Critical Implementation Paths
1.  **Notification Submission:**
    *   Client sends `POST` request to `/notification-service/notifications`.
    *   FastAPI validates request using Pydantic models.
    *   Generate unique `notificationId`.
    *   **Atomic Operation:**
        *   Begin SQLite transaction.
        *   Insert notification record into `notifications` table (status: `PENDING`).
        *   Publish notification message (JSON) to RabbitMQ `notification_tasks` queue.
        *   Commit SQLite transaction.
    *   Return `202 Accepted` with `notificationId`.
    *   Rollback transaction and return error if any step fails.
2.  **Notification Processing (Stub Worker):**
    *   Worker connects to RabbitMQ and subscribes to `notification_tasks`.
    *   On message receipt:
        *   Deserialize JSON message.
        *   Log received notification.
        *   **Atomic Operation:**
            *   Begin SQLite transaction.
            *   Update notification status in `notifications` table to `PROCESSING_STUB` using `id`.
            *   Commit SQLite transaction.
        *   Acknowledge RabbitMQ message.
    *   Rollback transaction and potentially re-queue/log error if DB update fails.
