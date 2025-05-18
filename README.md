# Notification Hub Demo(Live Site: https://notify.masoomchoudhury.com)

A multi-channel notification service built with Python, FastAPI, RabbitMQ, and SQLite, containerized with Docker. This project demonstrates the ability to integrate various third-party notification providers and manage asynchronous notification delivery.

**Assignment by Masoom Kumar Choudhury**

## Features

*   **Multi-Channel Notifications:**
    *   SMS (Textbee, Twilio, AWS SNS)
    *   Email (AWS SES)
    *   Android Push Notifications (via AWS SNS/FCM - Backend Implemented)
*   **Multiple SMS Gateway Integrations:**
    *   Textbee (Fully configured for live demo via UI)
    *   Twilio (Integrated, requires user credentials for UI testing)
    *   AWS SNS (Integrated, requires user credentials & AWS sandbox configuration for UI testing)
*   **Email Integration:**
    *   AWS SES (Integrated, requires user credentials & AWS sandbox configuration for UI testing)
*   **Asynchronous Processing:** Uses RabbitMQ for queuing notification tasks.
*   **Persistent Storage:** SQLite database for notification status, details, and push notification subscriptions.
*   **Interactive Frontend:** A simple HTML frontend to send SMS/Email notifications and view SMS gateway status notes.
*   **Contact Owner Feature:** Allows testers to send their contact details to the project owner via SMS for easier verification on sandboxed AWS services.
*   **Containerized:** Fully containerized with Docker and Docker Compose.
*   **Conceptual Stubs:** In-App notification channel is present in models but not functionally implemented.

## Technologies Used

*   **Backend:** Python, FastAPI
*   **Message Queue:** RabbitMQ
*   **Database:** SQLite (with `aiosqlite` for async access)
*   **Containerization:** Docker, Docker Compose
*   **Frontend:** HTML, Tailwind CSS (via CDN), JavaScript
*   **SMS Providers:**
    *   Textbee (via HTTPX)
    *   Twilio (via `twilio` library - *assumed, or direct HTTP*)
    *   AWS SNS (via `boto3`)
*   **Email Provider:**
    *   AWS SES (via `boto3`)
*   **Push Notification Provider:**
    *   AWS SNS for FCM (via `boto3`)

## Project Structure

```
.
├── app/                    # Main application code
│   ├── providers/          # Integration logic for SMS/Email/Push providers
│   │   ├── sms_textbee_provider.py
│   │   ├── sms_twilio_provider.py
│   │   ├── sms_aws_sns_provider.py
│   │   ├── push_sns_provider.py
│   │   └── ...
│   ├── __init__.py
│   ├── config.py           # Configuration management (reads .env)
│   ├── database.py         # SQLite database interactions
│   ├── email_service.py    # Logic for sending emails (e.g., via SES)
│   ├── main.py             # FastAPI application, API endpoints
│   ├── models.py           # Pydantic models for data validation & DB schema
│   ├── queue.py            # RabbitMQ interactions
│   ├── sms_service.py      # Logic for dispatching SMS to providers
│   └── worker.py           # Worker process to consume from RabbitMQ
├── static/
│   └── frontend.html       # Interactive web UI
├── .env.example            # Example environment file (user should rename to .env)
├── docker-compose.yml      # Docker Compose configuration
├── Dockerfile              # Dockerfile for the application
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Setup and Running Locally

1.  **Prerequisites:**
    *   Docker Desktop (or Docker Engine + Docker Compose) installed.
    *   Git (for cloning, if applicable).

2.  **Clone the Repository (if applicable):**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

3.  **Configure Environment Variables:**
    *   Create a `.env` file in the project root (you can copy `.env.example` if provided, or use the structure below).
    *   Fill in the necessary credentials. **For the live Textbee demo via the UI, ensure `TEXTBEE_API_KEY` and `TEXTBEE_DEVICE_ID` are correctly set.**
        ```env
        # --- General ---
        DATABASE_URL=sqlite+aiosqlite:///./data/notifications.db
        RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
        API_BASE_PATH=/notification-service
        EMAIL_SENDER=your_verified_ses_sender@example.com # For AWS SES

        # --- Textbee (Configured for Live Demo via UI) ---
        TEXTBEE_API_KEY=your_textbee_api_key_here 
        TEXTBEE_DEVICE_ID=your_textbee_device_id_here

        # --- AWS Credentials (for SES Email & SNS SMS/Push) ---
        AWS_ACCESS_KEY_ID=
        AWS_SECRET_ACCESS_KEY=
        AWS_REGION_NAME=your_aws_region # e.g., us-east-1
        
        # --- AWS SNS Specific (for SMS & Push) ---
        SNS_SENDER_ID= # Optional: Your AWS SNS Sender ID for SMS
        SNS_SMS_TYPE=Transactional # Or Promotional
        SNS_PLATFORM_APPLICATION_ARN_ANDROID= # CRITICAL for Android Push

        # --- Twilio (for SMS) ---
        TWILIO_ACCOUNT_SID=
        TWILIO_AUTH_TOKEN=
        TWILIO_MESSAGING_SERVICE_SID= # Either this OR TWILIO_FROM_NUMBER
        TWILIO_FROM_NUMBER=           # A Twilio phone number
        ```

4.  **Build and Run Containers:**
    *   From the project root directory, run:
        ```bash
        docker-compose up --build -d
        ```

5.  **Access the Application:**
    *   Frontend UI: `http://localhost:8000/static/frontend.html`
    *   API Docs (Swagger): `http://localhost:8000/docs`
    *   RabbitMQ Management UI: `http://localhost:15672` (user: `guest`, pass: `guest`)

6.  **Database Initialization:**
    *   The database (`notifications.db`) is created automatically. If schema changes occur (e.g., after pulling updates or modifying `app/models.py`), delete `db_data/notifications.db` and restart containers:
        ```bash
        rm -f db_data/notifications.db
        docker-compose down && docker-compose up --build -d
        ```

## Testing the Integrations

The frontend (`frontend.html`) allows sending SMS and Email notifications and provides notes on SMS gateway status.

*   **Textbee (SMS):**
    *   **Status:** Fully configured and operational for this demo using the credentials provided in `.env`.
    *   **Testing (UI):** Select "SMS", choose "Textbee", enter a 10-digit Indian mobile number, message, and send.

*   **Twilio (SMS):**
    *   **Status:** Integrated. Requires your Twilio Account SID, Auth Token, and a sending number/Messaging Service SID in `.env`.
    *   **Limitations:** Trial accounts may have restrictions. A paid plan is typically needed for full functionality.
    *   **Testing (UI):** If configured, select "Twilio" and send.

*   **Amazon SNS (SMS):**
    *   **Status:** Integrated. Requires AWS credentials in `.env`.
    *   **Limitations:** The AWS account is likely in the **SMS sandbox**. SMS messages can only be delivered to phone numbers verified in your AWS SNS console.
    *   **Testing (UI):** Verify a recipient number in your AWS SNS console. Then, select "Amazon SNS" and send to that verified number.

*   **AWS SES (Email):**
    *   **Status:** Integrated. Requires AWS credentials and a verified `EMAIL_SENDER` in `.env`.
    *   **Limitations:** The AWS account is likely in the **SES sandbox**. Emails can only be sent to/from email addresses/domains verified in your AWS SES console.
    *   **Testing (UI):** Verify a recipient email in your AWS SES console. Then, select "Email" and send.

*   **Android Push (AWS SNS/FCM):**
    *   **Status:** Backend is implemented. Requires AWS credentials and `SNS_PLATFORM_APPLICATION_ARN_ANDROID` in `.env`.
    *   **Functionality:** The system can store FCM device tokens against user IDs and send push messages to these devices via AWS SNS.
    *   **Testing (API - No UI Element for this):**
        1.  An Android app is needed to obtain an FCM registration token.
        2.  Register the device via API: `POST /notification-service/users/{user_id}/android-sns-subscriptions` with payload `{"user_id": "some_user", "fcm_token": "your_fcm_token"}`.
        3.  Send a push notification via API: `POST /notification-service/notifications` with payload `{"channel": "PUSH_ANDROID", "user_id": "some_user", "push_title": "Test Push", "message_body": "Hello from Push!"}`.
    *   **Note:** This demonstrates backend capability. The current `frontend.html` does not include UI for PUSH_ANDROID channel selection or device registration.

*   **In-App Notifications:**
    *   **Status:** Conceptual stub only. Not functionally implemented for delivery.

*   **"Help Test Other Gateways/Email?" Feature (Frontend):**
    *   Allows a tester to send their phone/email to the project owner (`+918249019575` via Textbee) for potential verification in AWS sandboxes.

## Stopping the Application

```bash
docker-compose down
```

## Future Enhancements (Potential)

*   UI elements for PUSH_ANDROID channel and device registration.
*   Full implementation of In-App notification channel.
*   More robust error handling and retry mechanisms.
*   Production-grade logging and monitoring.
