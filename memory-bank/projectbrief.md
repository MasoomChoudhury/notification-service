# Project Brief

## Project Name
Notification Service (Containerized Python Edition)

## Core Requirements
- Build a system to send Email, SMS, and In-App notifications.
- Implement a `POST /notifications` endpoint for queuing notifications.
- Develop a worker to process queued notifications.

## Project Goals
- Create a robust, scalable, and maintainable notification system.
- Ensure reliable delivery of notifications.
- Provide a clear API for other services to integrate with.

## Scope
- **Initial Phase:**
    - FastAPI application setup.
    - Docker and Docker Compose configuration.
    - SQLite database integration with robust settings.
    - RabbitMQ integration for message queuing.
    - Implementation of `POST /notification-service/notifications` endpoint.
    - Stub worker to consume messages and update notification status.
- **Future Phases (Implied):**
    - Integration with AWS SES for email.
    - Integration with Twilio for SMS.
    - Implementation of In-App notification logic.
    - Full worker implementation for sending notifications.
    - Optional `users` table and related functionality.

## API Base Path
`https://masoomchoudhury.com/notification-service/`
