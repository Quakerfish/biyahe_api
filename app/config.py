from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASS: str

    SESSION_SECRET_KEY: str
    SESSION_SAME_SITE: str = "lax"   # "lax" | "strict" | "none"
    SESSION_HTTPS_ONLY: bool = True

    CORS_ORIGINS: str = ""          # comma-separated

    # Read directly from env by the vercel-sdk Blob client too, but kept here
    # so Pydantic validates it's actually set before the app starts serving.
    # Named BIYAHE_READ_WRITE_TOKEN, not the usual BLOB_READ_WRITE_TOKEN -
    # Vercel auto-renamed it when the new Blob store was connected, since
    # the old store (since deleted) hadn't released the "BLOB" name prefix
    # yet at the time.
    BIYAHE_READ_WRITE_TOKEN: str = ""

    # --- Login OTP (email 2FA) ---
    # Same EmailJS account/service/template the Android app used to call
    # directly - just called from here instead, so the keys (especially
    # EMAILJS_PRIVATE_KEY, which is a real access token) never ship in the APK.
    EMAILJS_SERVICE_ID: str = ""
    EMAILJS_TEMPLATE_ID: str = ""
    EMAILJS_PUBLIC_KEY: str = ""
    EMAILJS_PRIVATE_KEY: str = ""
    # Optional separate template for the forgot-password email. Falls back to
    # EMAILJS_TEMPLATE_ID when empty (the same {{to_email}} / {{passcode}} template works).
    EMAILJS_RESET_TEMPLATE_ID: str = ""

    OTP_EXPIRY_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    # Matches the Android app's existing 45-second resend countdown UI.
    OTP_RESEND_COOLDOWN_SECONDS: int = 45

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()