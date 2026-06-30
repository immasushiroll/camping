#!/usr/bin/env python3
"""
check_jobs.py

Manually-triggered pipeline (run this yourself whenever you want to check
for new postings - no automatic trigger/cron/systemd attached):

  1. SCREENSHOT  - opens one visible Chrome window via Selenium, navigates
                    to each career page URL in turn, takes a full-page
                    screenshot of each (via Chrome DevTools Protocol).
  2. OCR         - runs local Tesseract OCR over each screenshot to pull
                    out raw (noisy) text.
  3. STRUCTURE   - Gemini pass #1: cleans the noisy OCR text into a
                    structured list of {position, date_posted_raw} per page.
  4. RECENCY     - Gemini pass #2: judges each posting's date_posted_raw
                    against today's date, drops anything 3+ days stale.
  5. KEYWORDS    - deterministic (non-AI) substring filter against your
                    target role keywords list.
  6. REPORT      - prints a formatted report directly to your terminal
                    (this script is meant to be run FROM a terminal, so no
                    separate popup window is needed - you're already there).

Requires:
  - GEMINI_API_KEY environment variable set.
  - Google Chrome or Chromium installed.
  - selenium, pytesseract, pillow, requests (pip install --break-system-packages)
  - tesseract-ocr system package (provides the `tesseract` binary pytesseract wraps)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

from screenshot import screenshot_career_pages
from ocr import ocr_all_screenshots
from gemini_structure import structure_all_pages
from gemini_filter_recency import filter_stale_postings, STALE_THRESHOLD_DAYS
from keyword_filter import filter_by_keywords, KEYWORDS

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# Placeholder URLs - replace with the real career pages you want to check.
CAREER_PAGES = [
"https://www.pinterestcareers.com/jobs/?search=&location=Toronto&team=Engineering&team=Finance&team=IT&team=Product&team=Sales&team=Trust+%26+Safety&type=Regular&type=Temporary+%28Fixed+Term%29&pagesize=20#results",
"https://www.amazon.jobs/en-gb/search?offset=0&result_limit=10&sort=recent&distanceType=Mi&radius=24km&industry_experience=less_than_1_year&latitude=43.64869&longitude=-79.38544&loc_group_id=&loc_query=Toronto%2C%20ON%2C%20Canada&base_query=&city=Toronto&country=CAN&region=Ontario&county=Toronto&query_options=&"
"https://jobs.rbc.com/ca/en/c/technology-analytics-research-jobs",
"https://recruiting.ultipro.ca/MER5001MCUL/JobBoard/6c1f133f-d0ac-48cd-a17d-bc54fe044ce3/?q=&o=postedDateDesc&w=Toronto%2C+ON%2C+CAN&wc=-79.383907%2C43.653524&we=-79.89990700000001%2C44.169523999999996%7C-78.867907%2C43.137524&wpst=2&f6=1",
"https://jobs.rbc.com/ca/en/capital-markets",
"https://www.linkedin.com/jobs/search-results/?currentJobId=3852113363&keywords=entry-level%20data%20posted%20in%20the%20past%203%20days&origin=SEMANTIC_SEARCH_LANDING_PAGE"
]
SCREENSHOTS_BASE_DIR = Path("screenshots")
# SCREENSHOTS_BASE_DIR = Path(__name__).parent / "screenshots"

# ---------------------------------------------------------------------------
# REPORT FORMATTING
# ---------------------------------------------------------------------------

def build_report(final_results: dict[str, list[dict]]) -> str:
    if not final_results:
        return "No matching, fresh, entry-relevant postings found this run.\n"

    lines = []
    total = sum(len(v) for v in final_results.values())
    lines.append("=" * 70)
    lines.append(f"  JOB CHECKER — {total} matching posting(s) found")
    lines.append("=" * 70)
    lines.append("")

    for url, postings in final_results.items():
        lines.append(f"SOURCE: {url}")
        lines.append("-" * 70)
        for p in postings:
            lines.append(f"  • {p['position']}")
            age = p.get("resolved_age_description", "")
            if age:
                lines.append(f"      age: {age}")
            lines.append("")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------

def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print(
            "[FATAL] GEMINI_API_KEY environment variable is not set. "
            "Export it before running this script.",
            file=sys.stderr,
        )
        return 1

    # with tempfile.TemporaryDirectory(prefix="job-checker-screenshots-") as tmp_dir:
    #     screenshot_dir = Path(tmp_dir)

    run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_dir = SCREENSHOTS_BASE_DIR / run_timestamp
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== STAGE 1: SCREENSHOTS ===")
    screenshots = screenshot_career_pages(CAREER_PAGES, screenshot_dir)
    if not screenshots:
        print("[FATAL] No screenshots were captured. Aborting.", file=sys.stderr)
        return 1

    print("\n=== STAGE 2: OCR ===")
    ocr_results = ocr_all_screenshots(screenshots)
    if not ocr_results:
        print("[FATAL] OCR produced no usable text. Aborting.", file=sys.stderr)
        return 1

    print("\n=== STAGE 3: GEMINI STRUCTURING ===")
    structured_results = structure_all_pages(ocr_results)
    if not structured_results:
        print("No postings could be extracted from any page.")
        return 0

    print(f"\n=== STAGE 4: GEMINI RECENCY FILTER (threshold: {STALE_THRESHOLD_DAYS} days) ===")
    fresh_results = filter_stale_postings(structured_results)
    if not fresh_results:
        print("No fresh postings remain after recency filtering.")
        return 0

    print("\n=== STAGE 5: DETERMINISTIC KEYWORD FILTER ===")
    final_results = filter_by_keywords(fresh_results, KEYWORDS)

    print("\n=== REPORT ===\n")
    report = build_report(final_results)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
