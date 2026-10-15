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
    # Comma separated list of origins allowed to call the API (CORS). Defaults to the local
    # Next.js dev server; set to the deployed frontend's origin(s) in production via env var.
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # --- Auth ---
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    # 4 hours: long enough for a normal working session, short enough that a leaked/forgotten
    # token (e.g. on a shared machine) doesn't stay valid indefinitely. No refresh-token flow is
    # implemented - when a token expires the user simply logs in again (see README).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 240
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # --- OCR (PaddleOCR: local, free, no API key - distinct from AI vision interpretation) ---
    OCR_ENABLED: bool = True
    OCR_LANGUAGE: str = "en"
    OCR_USE_GPU: bool = False
    PDF_RENDER_DPI: int = 288
    OCR_CONFIDENCE_THRESHOLD: float = 0.5
    # Deskew defaults off: the minAreaRect-based angle estimate is unreliable on sparse/
    # high-aspect-ratio text layouts (verified empirically - it can rotate otherwise-straight
    # text and hurt recognition). Turn it on for genuinely skewed scans via config.
    OCR_PREPROCESS_DESKEW: bool = False
    OCR_PREPROCESS_CLAHE: bool = True
    OCR_PREPROCESS_DENOISE: bool = False

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip().lower() for e in self.ALLOWED_EXTENSIONS.split(",") if e.strip()]

    @property
    def ai_mode(self) -> str:
        return "openai" if self.OPENAI_API_KEY else "demo"


@lru_cache
def get_settings() -> Settings:
    return Settings()
