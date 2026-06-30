"""
gemini_structure.py

Stage 1 of the two-pass Gemini pipeline: takes noisy raw OCR text from a
career page screenshot and asks Gemini to extract a clean, structured list
of job postings, each with just {position, date_posted_raw}.

OCR output is messy (misread characters, garbled spacing, navigation/footer
junk mixed in with actual postings) - Gemini is asked to use its judgment
to recover the intended text despite this, not to validate it strictly.

date_posted_raw is kept as whatever text Gemini can recover describing
when the post was made (e.g. "2 days ago", "Posted today", "March 3, 2026",
or "" if nothing usable is present) - actual stale/fresh filtering happens
in stage 2 (gemini_filter_recency.py), not here.
"""

import json
import os
import sys

import requests

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
GEMINI_TIMEOUT = 60

STRUCTURE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "postings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "position": {
                        "type": "string",
                        "description": (
                            "The cleaned-up job title, with OCR garbling "
                            "corrected as best as possible (e.g. 'Pata "
                            "Analyst' -> 'Data Analyst')."
                        ),
                    },
                    "date_posted_raw": {
                        "type": "string",
                        "description": (
                            "Whatever text describes when this was posted, "
                            "cleaned up (e.g. '2 days ago', 'Posted today', "
                            "'March 3, 2026'). Empty string if no date "
                            "information is present near this posting at all."
                        ),
                    },
                },
                "required": ["position", "date_posted_raw"],
            },
        }
    },
    "required": ["postings"],
}


def build_structure_prompt(raw_ocr_text: str) -> str:
    return (
        "The following text was extracted via OCR from a screenshot of a "
        "company career/jobs page. OCR introduces noise: misread letters, "
        "garbled spacing, words run together or split apart, and unrelated "
        "navigation/footer/header text mixed in with the actual job "
        "postings.\n\n"
        "Your task: identify every actual JOB POSTING in this text, and "
        "for each one extract:\n"
        "1. position - the job title, with obvious OCR errors corrected "
        "using your best judgment (e.g. 'Pata Analyst' is almost certainly "
        "'Data Analyst', 'Engineer' is almost certainly 'Engineer').\n"
        "2. date_posted_raw - any nearby text indicating when it was "
        "posted (e.g. '2 days ago', 'Posted today', a specific date). If "
        "no date info appears near a given posting, use an empty string - "
        "do not guess or fabricate a date.\n\n"
        "Ignore navigation links, footer text, company boilerplate, and "
        "anything that isn't actually a job posting title.\n\n"
        "Raw OCR text:\n"
        "---\n"
        f"{raw_ocr_text}\n"
        "---"
    )


def call_gemini_structure(raw_ocr_text: str) -> list[dict]:
    """
    Sends raw OCR text to Gemini, returns a list of
    {position, date_posted_raw} dicts. Returns [] on any failure.
    """
    if not raw_ocr_text.strip():
        return []

    if not GEMINI_API_KEY:
        print(
            "[ERROR] GEMINI_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        return []

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": build_structure_prompt(raw_ocr_text)}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": STRUCTURE_RESPONSE_SCHEMA,
        },
    }

    try:
        resp = requests.post(
            GEMINI_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            json=payload,
            timeout=GEMINI_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Gemini structure call failed: {e}", file=sys.stderr)
        return []

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        return parsed.get("postings", [])
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"[ERROR] Failed to parse Gemini structure response: {e}", file=sys.stderr)
        print(f"[DEBUG] Raw response: {resp.text[:1000]}", file=sys.stderr)
        return []


def structure_all_pages(ocr_results: dict[str, str]) -> dict[str, list[dict]]:
    """
    Takes {url: raw_ocr_text}, returns {url: [{position, date_posted_raw}]}.
    """
    structured = {}
    for url, raw_text in ocr_results.items():
        print(f"[INFO] Structuring OCR text via Gemini for {url}")
        postings = call_gemini_structure(raw_text)
        if postings:
            structured[url] = postings
        else:
            print(f"[WARN] No postings extracted for {url}", file=sys.stderr)
    return structured
