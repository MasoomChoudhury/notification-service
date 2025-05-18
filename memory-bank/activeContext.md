# Active Context

## Current Work Focus
-   **COMPLETED: Replaced `httpSMS` with `Textbee` Provider.**
    -   Created `app/providers/sms_textbee_provider.py` using the API details provided by the user (endpoint `https://api.textbee.dev/api/v1/gateway/devices/YOUR_DEVICE_ID/send-sms`, `POST` method, JSON body with `recipients` array and `message`, `x-api-key` header).
    -   Updated `app/config.py` and `docker-compose.yml` to include `TEXTBEE_API_KEY` and `TEXTBEE_DEVICE_ID`, removing `httpSMS` variables.
    -   Updated `app/models.py` `SmsProviderEnum` to replace `HTTP_SMS` with `TEXTBEE`.
    -   Updated `app/sms_service.py` to use `sms_textbee_provider` and check for `TEXTBEE_API_KEY`, `TEXTBEE_DEVICE_ID`.
    -   Updated `app/providers/__init__.py` to import `sms_textbee_provider` instead of `sms_http_provider`.
    -   Deleted `app/providers/sms_http_provider.py`.

## Recent Changes
-   Replaced the `httpSMS` provider with the `Textbee` provider using the API documentation details provided by the user.
-   The system now has functional backend code for Email (SES), SMS (Twilio, AWS SNS, Textbee), and Android Push (AWS SNS).

## Next Steps
1.  **User External Setup & Configuration (Crucial for Testing All Channels):**
    *   AWS SES: Verify sender email, manage sandbox.
    *   Firebase & AWS SNS for Push: Set up FCM project, SNS Platform Application.
    *   Update `.env` with all credentials: AWS (SES, SNS SMS, SNS Push), Twilio, Textbee (API key and Device ID).
2.  **Database Recreation (User Task):**
    *   User to delete `db_data/notifications.db` (due to multiple schema changes and provider enum change).
3.  **Rebuild and Restart Services (User Task):**
    *   User to run `docker-compose down` and then `docker-compose up --build -d`.
4.  **Comprehensive End-to-End Testing (User Task):**
    *   Test device registration for push notifications.
    *   Test sending Email (SES), SMS (Twilio, AWS SNS, Textbee), and Push (SNS Android) notifications via UI/API.
    *   Verify worker logs, message delivery, and provider dashboards for all channels.
5.  **Plan In-App Notification Logic.**
6.  **Address Pydantic V2 Warning.**
7.  **Review and Refine Error Handling & Retries for all services.**

## Active Decisions & Considerations
-   `Textbee` provider is now implemented based on the provided API reference. Its successful operation depends on the correctness of those details and the user's account status with Textbee.
-   The application is feature-complete for the requested notification channels from a backend perspective, pending full testing.

## Important Patterns & Preferences
-   Adherence to external API specifications for provider integrations.
-   Ensuring all relevant configuration files (`config.py`, `docker-compose.yml`, `.env` structure) are updated when changing providers.
-   Updating model enums (`SmsProviderEnum`) to reflect provider changes.

## Learnings & Project Insights
-   Having detailed API documentation is critical for correctly implementing third-party service integrations.
-   Changing a provider involves multiple touchpoints in the codebase: provider module, configuration, service dispatch logic, and data models.
