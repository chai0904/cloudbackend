from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    APP_NAME: str = "EduNexis"
    AUTH_MODE: Literal["firebase", "mock"] = "mock"

    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    FIREBASE_CREDENTIALS_PATH: str = "./firebase-credentials.json"

    CORS_ORIGINS: str = "http://localhost:3000"

    EMAILJS_SERVICE_ID: str = ""
    EMAILJS_PUBLIC_KEY: str = ""
    EMAILJS_PRIVATE_KEY: str = ""
    EMAILJS_TEMPLATE_ID: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
