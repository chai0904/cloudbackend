import httpx
from app.core.config import settings

async def send_welcome_email(to_email: str, name: str, org_name: str, password: str):
    """
    Sends a welcome email with temporary password using EmailJS REST API.
    """
    if not settings.EMAILJS_SERVICE_ID or not settings.EMAILJS_PUBLIC_KEY or not settings.EMAILJS_TEMPLATE_ID or not settings.EMAILJS_PRIVATE_KEY:
        print("EmailJS credentials (including private key) not configured. Skipping welcome email.")
        return

    url = "https://api.emailjs.com/api/v1.0/email/send"
    
    payload = {
        "service_id": settings.EMAILJS_SERVICE_ID,
        "template_id": settings.EMAILJS_TEMPLATE_ID,
        "user_id": settings.EMAILJS_PUBLIC_KEY,
        "accessToken": settings.EMAILJS_PRIVATE_KEY,
        "template_params": {
            "to_email": to_email,
            "to_name": name,
            "org_name": org_name,
            "password": password
        }
    }

    print(f"\n[EmailJS] Sending welcome email to: {to_email}")
    print(f"[EmailJS] Service ID: {settings.EMAILJS_SERVICE_ID}")
    print(f"[EmailJS] Template ID: {settings.EMAILJS_TEMPLATE_ID}")
    print(f"[EmailJS] Payload Params: {payload['template_params']}\n")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            print(f"Welcome email sent successfully to {to_email}")
    except httpx.HTTPStatusError as e:
        print(f"Failed to send welcome email to {to_email}. Status code: {e.response.status_code}")
        print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"Failed to send welcome email to {to_email}: {e}")
