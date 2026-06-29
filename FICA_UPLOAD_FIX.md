# FICA Upload Fix

This update makes the public signing link more tolerant when checking uploaded FICA documents.

Fixes included:
- Accepts `Received`, `Reviewed`, and `Approved` FICA statuses.
- Handles status casing differences from older database records.
- Confirms the uploaded file exists before counting it.
- Adds a fallback scan of `UPLOAD_FOLDER/fica_app_<application_id>` so final submit does not incorrectly block the client after a successful upload.

Important Render note:
- `UPLOAD_FOLDER=app/static/uploads` is not ideal for long-term storage on Render.
- Use a persistent Render disk or external storage for production documents.
