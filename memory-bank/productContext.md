# Product Context

## Problem Statement
Applications often need to send various types of notifications (Email, SMS, In-App) to users. Managing these different channels, ensuring reliable delivery, and handling queuing and retries can be complex and repetitive for each application. This project aims to centralize notification logic into a dedicated service.

## Proposed Solution
A containerized microservice built with Python (FastAPI) that:
1.  Provides a simple API endpoint (`POST /notification-service/notifications`) for other services to submit notification requests.
2.  Queues notification tasks using RabbitMQ for asynchronous processing.
3.  Uses a SQLite database to store notification status and details with robust configurations for reliability.
4.  Will have workers that consume tasks from RabbitMQ and integrate with external services like AWS SES (for email) and Twilio (for SMS) to send notifications.
5.  Supports In-App notifications (details to be defined).
6.  Is deployed using Docker and Docker Compose for easy setup and scalability.

## User Experience Goals
-   **For Developers (API Consumers):**
    -   Simple, well-documented API for sending notifications.
    -   Reliable and timely queuing of notification requests.
    -   Clear feedback on request submission (e.g., `notificationId`).
-   **For End Users (Receiving Notifications):**
    -   Timely and accurate delivery of notifications through their preferred channels.
    -   (Implicit) No duplicate or missed critical notifications.
-   **For Operators/Maintainers:**
    -   Easy to deploy, monitor, and scale the service.
    -   Persistent storage for notification status and RabbitMQ messages.
    -   Clear logging for troubleshooting.
