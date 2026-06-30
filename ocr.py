"""
ocr.py

Runs local OCR (pytesseract / Tesseract) over each career-page screenshot
to extract raw text. This text is messy (job board layouts, navigation
cruft, etc. all get OCR'd too) - cleanup and structuring into actual
postings happens in the next stage via Gemini, not here.
"""

import sys
from pathlib import Path

import pytesseract
from PIL import Image


def ocr_screenshot(image_path: Path) -> str:
    """
    Runs Tesseract OCR over a single screenshot and returns the raw
    extracted text. Returns "" on failure (logged to stderr).
    """
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        print(f"[ERROR] OCR failed for {image_path}: {e}", file=sys.stderr)
        return ""


def ocr_all_screenshots(screenshots: dict[str, Path]) -> dict[str, str]:
    """
    Takes {url: screenshot_path}, returns {url: raw_ocr_text}.
    Skips (omits) any screenshot that produced empty/failed OCR text.
    """
    results = {}
    for url, path in screenshots.items():
        print(f"[INFO] Running OCR on {path} ({url})")
        text = ocr_screenshot(path)
        if text.strip():
            results[url] = text
        else:
            print(f"[WARN] OCR produced no text for {url}", file=sys.stderr)
    return results

# ocr_all_screenshots()    