from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.models.models import CatalogComponent

# Below this score a match is discarded rather than attached - an unrelated catalog row must
# never get silently linked to a component just because it was the "closest" of a bad lot.
MATCH_FLOOR = 0.72


def _normalize(text: str) -> str:
    """Strip everything but letters/digits and uppercase, so '6205-2RS', '6205 2rs' and
    '6205_2RS' all compare equal - OCR output is inconsistent about separators."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def match_catalog_component(
    part_number: str, description: str, catalog: list[CatalogComponent],
) -> tuple[CatalogComponent | None, float]:
    """Best-effort match of an OCR/vision-extracted component against the known component
    catalog, so a part the shop has bought before is recognized and cross-referenced
    automatically instead of landing in manual review every time.

    An exact normalized part-number match wins outright (score 1.0). Otherwise falls back to
    fuzzy similarity on part number and description, keeping the single best candidate -
    but only if it clears MATCH_FLOOR, so a weak/no match returns (None, 0.0) rather than
    attaching a wrong catalog row.
    """
    if not catalog:
        return None, 0.0

    norm_pn = _normalize(part_number)
    best_item: CatalogComponent | None = None
    best_score = 0.0

    for item in catalog:
        item_pn = _normalize(item.part_number)
        if norm_pn and item_pn and norm_pn == item_pn:
            return item, 1.0

        score = 0.0
        if norm_pn and item_pn:
            score = SequenceMatcher(None, norm_pn, item_pn).ratio()
        if description and item.description:
            # Description-only similarity is weaker evidence than a part-number match, so it
            # is discounted - it can corroborate a borderline part-number score but shouldn't
            # on its own push an unrelated part over the floor.
            desc_score = SequenceMatcher(None, description.lower(), item.description.lower()).ratio()
            score = max(score, desc_score * 0.85)

        if score > best_score:
            best_item, best_score = item, score

    if best_score < MATCH_FLOOR:
        return None, 0.0
    return best_item, round(best_score, 3)
