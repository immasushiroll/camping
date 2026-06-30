"""
gemini_filter_recency.py

Stage 2 of the two-pass Gemini pipeline: takes the cleaned
{position, date_posted_raw} list from stage 1 and asks Gemini to resolve
each date_posted_raw into an actual freshness judgment - is this posting
3 or more days old (stale) given TODAY's date, or fresh enough to keep?

This is a separate pass (not merged into stage 1) because date resolution
("2 days ago" relative to today, "March 3" needing a year assumed, etc.)
is a distinct reasoning task from OCR cleanup, and keeping them separate
makes each prompt simpler and easier to debug independently.

Postings with no usable date info at all (empty date_posted_raw) are kept
by default rather than dropped - we have no evidence they're stale, so we
don't penalize them for missing data.
"""

import json
import os
import sys
from datetime import date

import requests

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
GEMINI_TIMEOUT = 60

STALE_THRESHOLD_DAYS = 3  # postings this many days old or older are dropped

RECENCY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "0-based index matching the input posting list order.",
                    },
                    "is_stale": {
                        "type": "boolean",
                        "description": (
                            f"True if the posting is {STALE_THRESHOLD_DAYS} or "
                            "more days old based on date_posted_raw and "
                            "today's date. False if it's fresher than that, "
                            "OR if date_posted_raw is empty/unusable (give "
                            "benefit of the doubt when date can't be determined)."
                        ),
                    },
                    "resolved_age_description": {
                        "type": "string",
                        "description": (
                            "Short description of how old this posting is "
                            "judged to be, e.g. '2 days old', 'unknown - no "
                            "date info', '~10 days old'."
                        ),
                    },
                },
                "required": ["index", "is_stale", "resolved_age_description"],
            },
        }
    },
    "required": ["verdicts"],
}


def build_recency_prompt(postings: list[dict], today: date) -> str:
    lines = [
        f"Today's date is {today.isoformat()}.",
        "",
        f"For each job posting below, determine whether it is STALE - "
        f"meaning {STALE_THRESHOLD_DAYS} or more days old as of today - "
        f"based on its date_posted_raw field.",
        "",
        "Rules:",
        "- 'Posted today' / 'just posted' / '1 day ago' / '2 days ago' -> NOT stale.",
        f"- '{STALE_THRESHOLD_DAYS} days ago' or more, 'X weeks ago', 'X months "
        f"ago', or an absolute date more than {STALE_THRESHOLD_DAYS} days "
        f"before today -> STALE.",
        "- If date_posted_raw is empty or you genuinely cannot interpret it, "
        "mark is_stale = false (do not penalize missing data) and note "
        "this in resolved_age_description.",
        "- If an absolute date has no year, assume the most recent "
        "occurrence of that month/day relative to today.",
        "",
        "Postings:",
    ]
    for i, p in enumerate(postings):
        lines.append(
            f"[{i}] position: {p.get('position', '')!r} | "
            f"date_posted_raw: {p.get('date_posted_raw', '')!r}"
        )
    return "\n".join(lines)


def call_gemini_recency(postings: list[dict], today: date | None = None) -> dict[int, dict]:
    """
    Sends postings to Gemini for staleness judgment, returns
    {index: verdict_dict}. Returns {} on failure.
    """
    if not postings:
        return {}

    if not GEMINI_API_KEY:
        print(
            "[ERROR] GEMINI_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        return {}

    today = today or date.today()

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": build_recency_prompt(postings, today)}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RECENCY_RESPONSE_SCHEMA,
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
        print(f"[ERROR] Gemini recency call failed: {e}", file=sys.stderr)
        return {}

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        verdicts = parsed.get("verdicts", [])
        return {v["index"]: v for v in verdicts if "index" in v}
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"[ERROR] Failed to parse Gemini recency response: {e}", file=sys.stderr)
        print(f"[DEBUG] Raw response: {resp.text[:1000]}", file=sys.stderr)
        return {}


def filter_stale_postings(
    structured_results: dict[str, list[dict]], today: date | None = None
) -> dict[str, list[dict]]:
    """
    Takes {url: [{position, date_posted_raw}]}, returns the same shape but
    with stale postings removed and a 'resolved_age_description' field
    added to each surviving posting.
    """
    fresh_results = {}
    for url, postings in structured_results.items():
        print(f"[INFO] Checking recency via Gemini for {url}")
        verdicts = call_gemini_recency(postings, today=today)
        if not verdicts:
            # Failed entirely for this page - skip rather than guess.
            print(f"[WARN] Recency check failed for {url}, skipping page", file=sys.stderr)
            continue

        kept = []
        for i, posting in enumerate(postings):
            v = verdicts.get(i)
            if not v:
                continue
            if not v.get("is_stale"):
                posting_copy = dict(posting)
                posting_copy["resolved_age_description"] = v.get(
                    "resolved_age_description", ""
                )
                kept.append(posting_copy)

        if kept:
            fresh_results[url] = kept

    return fresh_results
