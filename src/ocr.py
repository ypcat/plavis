"""OCR the MND PLA-activity infographic and extract per-aircraft-type counts.

The infographic is a stylized poster with labels like ``J-16x4``, ``Su-30 x 2``,
``殲-16 x 4``, ``運-8電偵機 x1``, ``BZK-005 無人機 x2``. We support two OCR
backends; PaddleOCR is preferred (better on Chinese + Latin + digits), with
Tesseract (``chi_tra+eng``) as a lightweight fallback.

The matcher is deliberately loose: it scans the OCR text for known aircraft
tokens and greedily attaches the nearest integer. Callers should treat the
output as best-effort.
"""

from __future__ import annotations

import io
import logging
import os
import re
from functools import lru_cache

log = logging.getLogger(__name__)

# Known PLA type tokens. Order matters: longer/more-specific first so ``Su-30MKK``
# wins over ``Su-30``. We also accept a handful of Chinese aliases.
TYPE_ALIASES: list[tuple[str, list[str]]] = [
    ("Su-30", [r"Su[\s\-]?30(?:MKK)?", r"蘇[\-]?30"]),
    ("J-10", [r"J[\s\-]?10[A-Z]?", r"殲[\-]?10"]),
    ("J-11", [r"J[\s\-]?11[A-Z]?", r"殲[\-]?11"]),
    ("J-16", [r"J[\s\-]?16[A-Z]?", r"殲[\-]?16"]),
    ("JH-7", [r"JH[\s\-]?7[A-Z]?", r"殲轟[\-]?7"]),
    ("H-6", [r"H[\s\-]?6[A-Z]?", r"轟[\-]?6"]),
    ("KJ-500", [r"KJ[\s\-]?500", r"空警[\-]?500"]),
    ("KJ-200", [r"KJ[\s\-]?200", r"空警[\-]?200"]),
    ("Y-8", [r"Y[\s\-]?8[A-Z]*", r"運[\-]?8"]),
    ("Y-9", [r"Y[\s\-]?9[A-Z]*", r"運[\-]?9"]),
    ("Y-20", [r"Y[\s\-]?20", r"運[\-]?20"]),
    ("BZK-005", [r"BZK[\s\-]?005"]),
    ("BZK-007", [r"BZK[\s\-]?007"]),
    ("TB-001", [r"TB[\s\-]?001"]),
    ("CH-4", [r"CH[\s\-]?4"]),
    ("WZ-7", [r"WZ[\s\-]?7", r"無偵[\-]?7"]),
    ("WZ-10", [r"WZ[\s\-]?10"]),
    ("Z-9", [r"Z[\s\-]?9"]),
    ("Z-18", [r"Z[\s\-]?18"]),
    ("Z-20", [r"Z[\s\-]?20"]),
    ("KA-28", [r"KA[\s\-]?28"]),
    ("Mi-17", [r"Mi[\s\-]?17"]),
]

COUNT_RE = r"(?:\s*[xX×*]\s*|\s+)(\d+)"


@lru_cache(maxsize=1)
def _paddle():
    try:
        from paddleocr import PaddleOCR  # type: ignore

        return PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    except Exception as e:  # pragma: no cover
        log.warning("paddleocr unavailable: %s", e)
        return None


def _ocr_paddle(image_bytes: bytes) -> str:
    ocr = _paddle()
    if ocr is None:
        return ""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img)
    result = ocr.ocr(arr, cls=True)
    lines: list[str] = []
    for block in result or []:
        for item in block or []:
            if not item or len(item) < 2:
                continue
            txt = item[1][0] if isinstance(item[1], (list, tuple)) else str(item[1])
            lines.append(txt)
    return "\n".join(lines)


def _ocr_tesseract(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except Exception as e:  # pragma: no cover
        log.warning("tesseract unavailable: %s", e)
        return ""
    img = Image.open(io.BytesIO(image_bytes))
    langs = os.environ.get("TESSERACT_LANGS", "chi_tra+eng")
    try:
        return pytesseract.image_to_string(img, lang=langs)
    except pytesseract.TesseractError as e:
        log.warning("tesseract error: %s", e)
        return ""


def ocr(image_bytes: bytes, backend: str | None = None) -> str:
    backend = (backend or os.environ.get("OCR_BACKEND") or "paddle").lower()
    if backend == "paddle":
        text = _ocr_paddle(image_bytes)
        if text:
            return text
        log.info("paddle returned empty; falling back to tesseract")
        return _ocr_tesseract(image_bytes)
    return _ocr_tesseract(image_bytes)


def extract_type_counts(text: str) -> dict[str, int]:
    """Scan OCR text and return ``{canonical_name: count}`` for known types."""
    if not text:
        return {}
    # Collapse whitespace — PaddleOCR often breaks ``J-16`` across lines.
    flat = re.sub(r"[\s\u3000]+", " ", text)
    counts: dict[str, int] = {}
    for canonical, aliases in TYPE_ALIASES:
        best = 0
        for alias in aliases:
            pattern = re.compile(alias + COUNT_RE, re.IGNORECASE)
            for m in pattern.finditer(flat):
                try:
                    n = int(m.group(1))
                except ValueError:
                    continue
                if 0 < n < 200:  # sanity clamp
                    best = max(best, n)
        if best > 0:
            counts[canonical] = best
    return counts


def extract_type_counts_from_image(image_bytes: bytes, backend: str | None = None) -> dict[str, int]:
    text = ocr(image_bytes, backend=backend)
    return extract_type_counts(text)
