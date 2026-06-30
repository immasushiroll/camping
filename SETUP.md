# Job Checker — Setup Instructions (v3: Screenshot + OCR + Gemini pipeline)

## What this does, in order

1. **Screenshot** — opens one visible Chrome window, visits each career
   page URL in `check_jobs.py`'s `CAREER_PAGES` list, and takes a
   full-page screenshot of each (using Chrome's own DevTools Protocol so
   it captures content below the fold too, not just what scrot would see
   in the current viewport).
2. **OCR** — runs local Tesseract OCR over each screenshot to pull out
   raw text. No API calls, no cost, fully offline.
3. **Gemini pass #1 (structuring)** — cleans the noisy OCR text into a
   list of `{position, date_posted_raw}` per page, correcting obvious OCR
   garbling (e.g. "Pata Analyst" → "Data Analyst").
4. **Gemini pass #2 (recency)** — given today's date, judges each
   `date_posted_raw` and drops anything 3+ days stale. Postings with no
   usable date info are kept (benefit of the doubt).
5. **Deterministic keyword filter** — plain substring matching against
   your role keywords list. No AI involved in this step, by design — this
   is the one stage you wanted to be fully predictable.
6. **Report** — printed directly to the terminal you ran the script from.
   There's no separate popup window in this version, since you're running
   this manually from a terminal already.

This is **manually triggered only** — no systemd service, no cron, no
login hook. You run it yourself whenever you want to check.

## 1. Install system dependencies (Arch Linux)

```bash
# Chrome or Chromium - either works. Chromium is in the official repos:
sudo pacman -S chromium
# OR, if you specifically want Google Chrome (AUR, needs an AUR helper):
yay -S google-chrome

# Tesseract OCR engine (the actual OCR binary pytesseract wraps)
sudo pacman -S tesseract tesseract-data-eng
```

Note: `chromedriver` does NOT need to be installed separately — Selenium
4's built-in Selenium Manager auto-downloads a matching driver the first
time you run the script (it needs network access for this one-time
download). If you'd rather pin a specific version yourself, `chromedriver`
is available in the AUR.

## 2. Install Python dependencies

```bash
pip install selenium pytesseract pillow requests --break-system-packages
```

## 3. Get a Gemini API key

If you don't already have one, create it in Google AI Studio (search
"Google AI Studio API key" if you need the current link).

## 4. Edit the config in check_jobs.py

- `CAREER_PAGES` — replace the placeholder URLs with your real career page
  URLs.
- Keyword list lives in `keyword_filter.py` (`KEYWORDS`) if you want to
  adjust your target roles.
- Stale threshold (`STALE_THRESHOLD_DAYS`, default 3) lives in
  `gemini_filter_recency.py` if you want to change it.

## 5. Put the files in place

All six files need to live together in the same directory (they import
from each other):

```bash
mkdir -p ~/job-checker
cp check_jobs.py screenshot.py ocr.py gemini_structure.py gemini_filter_recency.py keyword_filter.py ~/job-checker/
chmod +x ~/job-checker/check_jobs.py
```

## 6. Run it

```bash
export GEMINI_API_KEY=your-actual-key-here
cd ~/job-checker
python3 check_jobs.py
```

A Chrome window will pop open and visit each URL in turn (you'll see it
happening — it's not headless, per your request). Progress for each stage
prints to your terminal as it runs, ending with a formatted report of
whatever survived all the filters.

Consider adding `export GEMINI_API_KEY=...` to your `~/.bashrc` or
`~/.zshrc` so you don't have to re-export it every session.

## What was tested before delivery vs. what wasn't

**Tested (with mocked inputs, since I don't have your real URLs, a
working Gemini key, or a GUI in my sandbox to launch Chrome):**
- OCR stage: ran real Tesseract against a synthetic test image containing
  job-title-like text — confirmed it actually extracts garbled-but-usable
  text (e.g. "Junior Pata Analyst" instead of "Junior Data Analyst" — this
  is realistic OCR noise, not a bug, and is exactly what stage 3 is meant
  to clean up).
- Gemini structuring prompt + response parsing: verified against a
  realistic mocked API response shaped like Gemini's actual output format.
- Gemini recency prompt + filtering logic: verified a 1-week-old posting
  gets correctly dropped, a 2-day-old posting and a no-date posting both
  get correctly kept.
- Deterministic keyword filter: verified against mixed matching/non-matching
  titles.
- Full pipeline orchestration: ran `check_jobs.py`'s `main()` with every
  stage mocked, confirmed data flows correctly end-to-end and the final
  report only contains postings that survived every filter.
- Missing-API-key guard: confirmed the script fails fast with a clear
  error instead of opening Chrome first and failing later.

**NOT tested (couldn't be, in this environment):**
- An actual Selenium-driven Chrome window taking a real full-page
  screenshot of a real career page.
- A real Gemini API call (no key available here).
- Whether your specific career pages render postings in a way that OCR
  can usefully read (text size, contrast, layout all matter for OCR
  accuracy — some sites may need a longer wait time before screenshotting,
  or may have such ornate styling that OCR struggles).

**Recommendation:** run it manually against 1-2 of your real URLs first
and read the terminal output closely before trusting it across your whole
list. If OCR output looks too garbled for Gemini to recover reliably on a
specific site, that site may need the wait time increased (edit
`PAGE_LOAD_WAIT_SECONDS` in `screenshot.py`) or may just not be a good fit
for this approach.

## Known limitations

- **OCR accuracy depends entirely on how the page renders.** Small text,
  low contrast, unusual fonts, or dense layouts will produce noisier OCR
  output. Gemini's structuring pass is reasonably good at correcting
  typical OCR errors, but garbage in still means a higher chance of
  garbage out.
- **One Chrome window, sequential.** Pages are visited one at a time in a
  single window (per your choice) — this is slower than parallel tabs but
  simpler and more predictable.
- **Fixed 3-second wait.** Some heavy JS-rendered job boards (certain
  Greenhouse/Lever embeds) may need longer than 3 seconds to fully render
  postings. If you notice missing postings on a specific site, increase
  `PAGE_LOAD_WAIT_SECONDS` in `screenshot.py`.
- **Cost.** Two Gemini calls per career page per run (one structuring,
  one recency check). With `gemini-2.5-flash` this should be cheap, but
  it's not free — check current pricing if you run this very frequently
  across many URLs.
- **No history/dedup.** Every run re-evaluates the current state of each
  page from scratch — there's no memory of what you've already seen
  across runs.
