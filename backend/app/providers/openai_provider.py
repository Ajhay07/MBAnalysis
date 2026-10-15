from __future__ import annotations

import base64
import json
import time

from pydantic import ValidationError

from app.config import get_settings
from app.providers.base import DrawingAnalysisProvider
from app.schemas.analysis import AnalysisResult

SYSTEM_PROMPT = (
    "You are an expert mechanical engineering drawing analyst. Given an engineering drawing "
    "image and any OCR text extracted from it, extract the title block, dimensions, materials, "
    "and a list of candidate components/parts with their specs. Respond ONLY with JSON matching "
    "this shape: {\"provider\": str, \"title_block\": {\"drawing_number\": str, \"title\": str, "
    "\"revision\": str, \"units\": str, \"scale\": str, \"material_spec\": str}, "
    "\"dimensions\": [{\"label\": str, \"value\": str, \"tolerance\": str|null, \"page\": int, "
    "\"source_text\": str, \"confidence\": float}], \"materials\": [str], "
    "\"components\": [{\"part_number\": str, \"description\": str, \"category\": str, "
    "\"quantity\": float, \"material\": str, \"grade\": str, \"dimensions\": object, "
    "\"tolerances\": object, \"gear_specs\": object, \"make_buy\": \"Make\"|\"Buy\"|\"Review\", "
    "\"confidence\": float, \"verification_status\": str, \"source_page\": int, "
    "\"source_region\": object, \"source_text\": str}], \"raw_ocr_text\": str, "
    "\"overall_confidence\": float}. Never invent precise numeric values you cannot see; use low "
    "confidence and the Review classification when uncertain."
)

# Bounded timeout + retry/backoff for transient failures (timeout/rate-limit/connection/server
# errors). Auth errors are never retried - they fail fast with a clear, actionable reason.
REQUEST_TIMEOUT_SECONDS = 60
MAX_TRANSIENT_RETRIES = 2
BACKOFF_BASE_SECONDS = 1.5


class ProviderAuthError(Exception):
    """Non-retryable: bad/revoked API key or insufficient permissions. Fails fast."""


class ProviderTransientError(Exception):
    """Retryable failure (timeout/rate-limit/connection/server error) whose retries were
    exhausted, or a malformed AI JSON response that could not be parsed/validated."""


class OpenAIVisionProvider(DrawingAnalysisProvider):
    """Uses the official OpenAI python SDK with a vision-capable chat model to analyze a
    drawing image, returning Pydantic-validated structured JSON. Requires OPENAI_API_KEY."""

    name = "openai"

    def __init__(self):
        self.settings = get_settings()
        if not self.settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set; OpenAIVisionProvider cannot be used.")
        from openai import OpenAI  # imported lazily so demo mode never needs the package configured
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS)

    def _is_auth_error(self, exc: Exception) -> bool:
        try:
            from openai import AuthenticationError, PermissionDeniedError
            if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
                return True
        except Exception:  # pragma: no cover - openai package always available in practice
            pass
        status = getattr(exc, "status_code", None)
        return status in (401, 403)

    def _is_transient_error(self, exc: Exception) -> bool:
        try:
            from openai import APITimeoutError, APIConnectionError, RateLimitError, InternalServerError
            if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError)):
                return True
        except Exception:  # pragma: no cover
            pass
        status = getattr(exc, "status_code", None)
        return status in (408, 409, 429, 500, 502, 503, 504)

    def _call_with_retry(self, **kwargs):
        last_exc: Exception | None = None
        for attempt in range(MAX_TRANSIENT_RETRIES + 1):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as exc:
                if self._is_auth_error(exc):
                    raise ProviderAuthError(f"OpenAI authentication/authorization failed: {exc}") from exc
                if self._is_transient_error(exc) and attempt < MAX_TRANSIENT_RETRIES:
                    last_exc = exc
                    time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
                    continue
                if self._is_transient_error(exc):
                    raise ProviderTransientError(
                        f"OpenAI request failed after {MAX_TRANSIENT_RETRIES} retries: {exc}") from exc
                # Unknown/non-retryable error - surface as-is.
                raise
        raise ProviderTransientError(f"OpenAI request failed after retries: {last_exc}")

    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str) -> AnalysisResult:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        response = self._call_with_retry(
            model=self.settings.OPENAI_VISION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"OCR text extracted from the drawing:\n{ocr_text}\n"
                                                  f"Known drawing number hint: {drawing_number}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProviderTransientError(f"AI provider returned malformed (non-JSON) response: {exc}") from exc
        data.setdefault("provider", "openai")
        data.setdefault("raw_ocr_text", ocr_text)
        try:
            return AnalysisResult.model_validate(data)
        except ValidationError as exc:
            raise ProviderTransientError(f"AI provider returned JSON that did not match the expected schema: {exc}") from exc
