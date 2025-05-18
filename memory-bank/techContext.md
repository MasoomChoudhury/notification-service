# Tech Context

## Technologies Used
-   **Programming Language:** Python 3.9+ (Assumption, common modern choice)
-   **Web Framework:** FastAPI
-   **ASGI Server:** Uvicorn
-   **Database:** SQLite
    -   Driver: `aiosqlite` (for asynchronous access from FastAPI)
-   **Message Queue:** RabbitMQ
    -   Client Library: `aio_pika` (preferred for async publishing/consuming) or `pika` (synchronous, potentially for a separate worker process)
-   **Containerization:** Docker, Docker Compose
-   **Data Validation/Serialization:** Pydantic (comes with FastAPI)
-   **Email Service (Future):** AWS SES (API integration, likely using `boto3`)
-   **SMS Service (Implemented):** Twilio (API integration, likely using `twilio` Python library), AWS SNS (using `boto3`), Textbee (direct HTTP API calls using `httpx`).
-   **Standard Libraries:** `json`, `uuid`, `logging`, `os`, `asyncio`

## Development Setup
-   **Prerequisites:** Docker Desktop (or Docker Engine + Docker Compose) installed.
-   **Configuration:**
    -   `Dockerfile` for building the FastAPI application image.
    -   `docker-compose.yml` to define and run `app` and `rabbitmq` services.
    -   Environment variables for database URL, RabbitMQ URL, etc., passed via `docker-compose.yml`.
-   **Running the Application:**
    ```bash
    docker-compose up --build
    ```
-   **Accessing Services:**
    -   FastAPI App: `http://localhost:8000` (or configured port)
    -   RabbitMQ Management UI: `http://localhost:15672` (or configured port)
-   **Database Persistence:** SQLite database file will be stored in `./db_data/notifications.db` on the host, mounted into the `app` container at `/app/data/notifications.db`.
-   **RabbitMQ Data Persistence:** RabbitMQ data will be stored in `./rabbitmq_data` on the host, mounted into the `rabbitmq` container.

## Technical Constraints
-   Must use Python with FastAPI.
-   Must use SQLite for the database in this initial phase.
-   Must use RabbitMQ for the message queue.
-   Must be containerized with Docker and Docker Compose.
-   API base path must be `https://masoomchoudhury.com/notification-service/`, which translates to a router prefix of `/notification-service` in FastAPI.

## Dependencies
*(To be listed in `requirements.txt`)*
-   `fastapi`
-   `uvicorn[standard]`
-   `aiosqlite`
-   `aio_pika` (or `pika`)
-   `pydantic` (comes with FastAPI, but good to be explicit if using advanced features or specific versions)
-   `python-dotenv` (for managing environment variables locally, if not solely relying on Docker Compose)
-   `requests` (general HTTP client, might be useful for future integrations or health checks if not using httpx)
-   `httpx` (for asynchronous HTTP requests, used by Textbee provider)
-   `boto3` (for AWS SES and AWS SNS)
-   `twilio` (for Twilio)

## Tool Usage Patterns
-   **Docker:** To build a consistent, portable image for the FastAPI application. Multi-stage builds will be used to keep the final image lean.
-   **Docker Compose:** To define and manage the multi-service environment (FastAPI app, RabbitMQ) for local development. Facilitates service discovery, port mapping, volume mounting, and environment variable configuration.
-   **Uvicorn:** As the ASGI server to run the FastAPI application.
-   **`aiosqlite`:** For all database interactions from the asynchronous FastAPI application to ensure non-blocking I/O.
-   **`aio_pika` / `pika`:** For publishing messages to RabbitMQ from the API and consuming messages in the worker. `aio_pika` is preferred for async environments.
-   **Pydantic:** For request/response model definition, validation, and serialization within FastAPI.
-   **Standard Python `logging`:** For application logging.
