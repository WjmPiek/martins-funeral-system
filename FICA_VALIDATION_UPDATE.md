# FICA Validation Update

This update changes FICA uploads from a simple "file received" check to a safer review workflow.

## New workflow

Missing -> Uploaded / Needs Review -> Reviewed / Rejected

## What the system checks automatically

- Allowed file extensions only: PDF, JPG, JPEG, PNG, WEBP
- File is not empty
- File is not too small
- File is not larger than 10 MB
- PDF text extraction where possible
- ID copy PDFs: tries to find the client's ID number
- Proof of address PDFs: tries to find address-like text and client name/surname
- Bank statement PDFs: checks for banking-related wording
- Passport / permit PDFs: checks for passport/permit wording

## Important

The system does not auto-approve FICA. It marks uploads as **Needs Review** unless a staff member approves them.

Images and scanned PDFs require manual staff review unless OCR is added later using Google Vision, AWS Textract, or Tesseract.

## Staff controls added

In Document Tracking -> Application Documents, staff can:

- View uploaded FICA files
- Approve a document
- Reject a document

All approve/reject actions are recorded in the audit log.
