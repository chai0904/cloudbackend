import httpx

try:
    response = httpx.post(
        "http://localhost:8000/api/auth/signup",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "organization_name": "Test Org"
        }
    )
    print("STATUS:", response.status_code)
    print("JSON:", response.json())
except Exception as e:
    print("ERROR:", e)
