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
    BLOB_READ_WRITE_TOKEN: str = ""

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
