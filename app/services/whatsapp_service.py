import os
import requests


def send_whatsapp_message(to_number: str, message: str) -> bool:
    """
    Sends a WhatsApp text message using Meta WhatsApp Cloud API.

    Required Render environment variables:
      WHATSAPP_ACCESS_TOKEN
      WHATSAPP_PHONE_NUMBER_ID
      WHATSAPP_ENABLED=true

    Phone number must be in international format, e.g. 27821234567.
    """
    enabled = os.getenv("WHATSAPP_ENABLED", "false").lower() in {"true", "1", "yes", "y"}
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    if not enabled:
        print("WHATSAPP NOT SENT - WHATSAPP_ENABLED is not true")
        return False

    if not token or not phone_number_id:
        print("WHATSAPP NOT SENT - configure WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID")
        return False

    to_number = "".join(ch for ch in str(to_number or "") if ch.isdigit())
    if to_number.startswith("0"):
        to_number = "27" + to_number[1:]

    if not to_number:
        print("WHATSAPP NOT SENT - missing client phone number")
        return False

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "preview_url": True,
            "body": message
        }
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code >= 400:
            print("WHATSAPP SEND FAILED:", response.status_code, response.text)
            return False
        print("WHATSAPP SENT:", response.text)
        return True
    except Exception as exc:
        print("WHATSAPP SEND ERROR:", exc)
        return False
