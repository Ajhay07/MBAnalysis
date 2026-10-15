from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OPENAI_API_KEY: str = ""
    OPENAI_VISION_MODEL: str = "gpt-4o-mini"
    DATABASE_URL: str = "sqlite:///./mbanalysis.db"
    MAX_UPLOAD_MB: int = 25
    ALLOWED_EXTENSIONS: str = ".pdf,.png,.jpg,.jpeg,.tif,.tiff"
    ENVIRONMENT: str = "development"
    UPLOAD_DIR: str = "./uploads"

    # --- Auth ---
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    # 4 hours: long enough for a normal working session, short enough that a leaked/forgotten
    # token (e.g. on a shared machine) doesn't stay valid indefinitely. No refresh-token flow is
    # implemented - when a token expires the user simply logs in again (see README).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 240
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip().lower() for e in self.ALLOWED_EXTENSIONS.split(",") if e.strip()]

    @property
    def ai_mode(self) -> str:
        return "openai" if self.OPENAI_API_KEY else "demo"


@lru_cache
def get_settings() -> Settings:
    return Settings()
