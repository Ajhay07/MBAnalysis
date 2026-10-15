from __future__ import annotations

import base64
import json

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


class OpenAIVisionProvider(DrawingAnalysisProvider):
    """Uses the official OpenAI python SDK with a vision-capable chat model to analyze a
    drawing image, returning Pydantic-validated structured JSON. Requires OPENAI_API_KEY."""

    name = "openai"

    def __init__(self):
        self.settings = get_settings()
        if not self.settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set; OpenAIVisionProvider cannot be used.")
        from openai import OpenAI  # imported lazily so demo mode never needs the package configured
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)

    def analyze(self, *, image_path: str, ocr_text: str, drawing_number: str) -> AnalysisResult:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        response = self.client.chat.completions.create(
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
        data = json.loads(content)
        data.setdefault("provider", "openai")
        data.setdefault("raw_ocr_text", ocr_text)
        return AnalysisResult.model_validate(data)
