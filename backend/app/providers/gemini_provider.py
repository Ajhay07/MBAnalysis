from __future__ import annotations

import json
import time

from pydantic import ValidationError

from app.config import get_settings
from app.providers.base import DrawingAnalysisProvider
from app.providers.openai_provider import (
    SYSTEM_PROMPT,
    REQUEST_TIMEOUT_SECONDS,
    MAX_TRANSIENT_RETRIES,
    BACKOFF_BASE_SECONDS,
    ProviderAuthError,
    ProviderTransientError,
)
from app.schemas.analysis import AnalysisResult

from pydantic import BaseModel
from pydantic_core import PydanticUndefined


def _normalize_nulls(data, model_cls: type[BaseModel]):
    """Gemini (observed live, unlike OpenAI's json_object mode) sometimes emits an explicit JSON
    null for an optional dict/string field instead of omitting it (e.g. title_block.scale: null,
    components[].source_region: null). Pydantic's strict dict/str field types reject None even
    when the field has a non-None default, so without this normalization every such response
    would be rejected as a schema violation. This walks the raw dict/list structure using the
    target model's own field defaults (never inventing a value - only replacing an explicit null
    with that field's declared default) before validation."""
    if not isinstance(data, dict):
        return data
    cleaned = dict(data)
    for field_name, field in model_cls.model_fields.items():
        if field_name not in cleaned:
            continue
        value = cleaned[field_name]
        annotation = field.annotation
        # Unwrap list[Model] / Model-typed fields to recurse into nested structures.
        origin = getattr(annotation, "__origin__", None)
        if origin in (list,):
            (item_type,) = getattr(annotation, "__args__", (None,))
            if value is None:
                cleaned[field_name] = field.default_factory() if field.default_factory else []
            elif isinstance(item_type, type) and issubclass(item_type, BaseModel) and isinstance(value, list):
                cleaned[field_name] = [_normalize_nulls(item, item_type) for item in value]
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            cleaned[field_name] = _normalize_nulls(value, annotation) if value is not None else value
        elif value is None:
            default = field.default
            if default is not PydanticUndefined and default is not None:
                cleaned[field_name] = default
            elif field.default_factory is not None:
                cleaned[field_name] = field.default_factory()
    return cleaned

# Reuses the exact same SYSTEM_PROMPT/schema contract and ProviderAuthError/ProviderTransientError
# exceptions as OpenAIVisionProvider so analysis_pipeline.py can treat every real provider
# identically - only the underlying SDK call differs.


def _image_mime_type(image_path: str) -> str:
    ext = image_path.rsplit(".", 1)[-1].lower() if "." in image_path else ""
    return {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "tif": "image/tiff", "tiff": "image/tiff",
    }.get(ext, "image/png")


class GeminiVisionProvider(DrawingAnalysisProvider):
    """Uses the official Google Gen AI Python SDK (google-genai) with a vision-capable Gemini
    model to analyze a drawing image, returning Pydantic-validated structured JSON against the
    exact same AnalysisResult schema as OpenAIVisionProvider/DemoProvider. Requires GEMINI_API_KEY."""

    name = "gemini"

    def __init__(self):
        self.settings = get_settings()
        if not self.settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set; GeminiVisionProvider cannot be used.")
        from google import genai  # imported lazily so demo/openai mode never needs this package
        self.client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        self.model = self.settings.GEMINI_MODEL

    def _is_auth_error(self, exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        return code in (401, 403)

    def _is_transient_error(self, exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        if code in (408, 409, 429, 500, 502, 503, 504):
            return True
        # Network/connection-level failures the SDK surfaces as plain exceptions (not APIError).
        from google.genai import errors as genai_errors
        return not isinstance(exc, genai_errors.APIError) and code is None and isinstance(
            exc, (TimeoutError, ConnectionError))

    def _is_blocked_response(self, response) -> str | None:
        """Gemini safety filtering doesn't raise - it returns a response with no candidates or a
        non-STOP finish_reason. Treated as a transient/clean failure (never silently fabricated)."""
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return "Gemini returned no candidates (likely blocked by safety filters)."
        finish_reason = getattr(candidates[0], "finish_reason", None)
        finish_reason_str = str(finish_reason) if finish_reason is not None else ""
        if finish_reason_str and finish_reason_str not in ("STOP", "FinishReason.STOP"):
            return f"Gemini response did not complete normally (finish_reason={finish_reason_str})."
        return None

    def _call_with_retry(self, **kwargs):
        from google.genai import errors as genai_errors
        last_exc: Exception | None = None
        for attempt in range(MAX_TRANSIENT_RETRIES + 1):
            try:
                return self.client.models.generate_content(**kwargs)
            except genai_errors.APIError as exc:
                if self._is_auth_error(exc):
                    raise ProviderAuthError(f"Gemini authentication/authorization failed: {exc}") from exc
                if self._is_transient_error(exc) and attempt < MAX_TRANSIENT_RETRIES:
                    last_exc = exc
                    time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
                    continue
                if self._is_transient_error(exc):
                    raise ProviderTransientError(
                        f"Gemini request failed after {MAX_TRANSIENT_RETRIES} retries: {exc}") from exc
                raise
            except Exception as exc:
                if self._is_transient_error(exc) and attempt < MAX_TRANSIENT_RETRIES:
                    last_exc = exc
                    time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
                    continue
                raise
        raise ProviderTransientError(f"Gemini request failed after retries: {last_exc}")

    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str) -> AnalysisResult:
        from google.genai import types

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        prompt_text = (
            f"{SYSTEM_PROMPT}\n\nOCR text extracted from the drawing:\n{ocr_text}\n"
            f"Known drawing number hint: {drawing_number}"
        )

        response = self._call_with_retry(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=_image_mime_type(image_path)),
                prompt_text,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
            ),
        )

        blocked_reason = self._is_blocked_response(response)
        if blocked_reason:
            raise ProviderTransientError(blocked_reason)

        content = response.text
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProviderTransientError(f"AI provider returned malformed (non-JSON) response: {exc}") from exc
        # Always stamped unconditionally (not setdefault) - the model sometimes fills its own
        # (wrong) value for "provider" despite the prompt instruction, e.g. observed live
        # returning "custom"; this field must reliably identify the real provider that produced
        # the result for the Analysis.provider column / UI badge, never a model-invented string.
        data["provider"] = "gemini"
        data.setdefault("raw_ocr_text", ocr_text)
        data = _normalize_nulls(data, AnalysisResult)
        try:
            return AnalysisResult.model_validate(data)
        except ValidationError as exc:
            raise ProviderTransientError(
                f"AI provider returned JSON that did not match the expected schema: {exc}") from exc
