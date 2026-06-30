"""
screenshot.py

Drives one persistent, VISIBLE Chrome window via Selenium, navigates to
each career page URL in turn, and takes a full-page screenshot of each
using the Chrome DevTools Protocol (CDP).

Why CDP instead of plain scrot: scrot only captures whatever's currently
rendered in the visible viewport - it has no concept of "the whole page."
CDP's Page.captureScreenshot with captureBeyondViewport=True asks Chrome
itself to render the entire document (even parts below the fold) into a
single image, which is exactly what we want for long job listing pages.

Falls back to a resize-window + driver.save_screenshot() approach if the
CDP capture fails on a given page (CDP screenshot capture has been
reported to be occasionally unstable on heavier/slower-rendering pages).
"""

import base64
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

PAGE_LOAD_WAIT_SECONDS = 3  # fixed pause after navigation, before screenshotting


def build_driver() -> webdriver.Chrome:
    """
    Launches a single, visible (non-headless) Chrome window. Selenium 4's
    built-in Selenium Manager will auto-download a matching chromedriver
    if one isn't already on PATH, so this should "just work" as long as
    Chrome or Chromium itself is installed.
    """
    options = Options()
    # NOT headless - a real visible window, per your setup.
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    # Helps avoid odd rendering states on some sites (popups, etc.)
    options.add_argument("--disable-infobars")

    try:
        driver = webdriver.Chrome(options=options)
    except WebDriverException as e:
        print(
            f"[FATAL] Could not start Chrome via Selenium: {e}\n"
            f"Make sure Google Chrome or Chromium is installed, and that "
            f"either chromedriver is on your PATH or Selenium Manager can "
            f"reach the network to download one.",
            file=sys.stderr,
        )
        raise
    return driver


def capture_full_page_screenshot(driver: webdriver.Chrome, out_path: Path) -> bool:
    """
    Takes a full-page screenshot of the currently loaded page and writes
    it to out_path. Returns True on success, False on failure.
    """
    try:
        metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
        content_size = metrics["contentSize"]
        result = driver.execute_cdp_cmd(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": True,
                "clip": {
                    "x": 0,
                    "y": 0,
                    "width": content_size["width"],
                    "height": content_size["height"],
                    "scale": 1,
                },
            },
        )
        png_bytes = base64.b64decode(result["data"])
        print(out_path.write_bytes(png_bytes))
        print(type(png_bytes))
        print("first case")
        return True
    except Exception as e:
        print(
            f"[WARN] CDP full-page screenshot failed ({e}); "
            f"falling back to resize+save_screenshot.",
            file=sys.stderr,
        )

    # Fallback: resize the window to the page's full scroll height, then
    # take a normal screenshot. Works in many cases even when CDP doesn't.
    try:
        total_height = driver.execute_script(
            "return Math.max(document.body.scrollHeight, "
            "document.documentElement.scrollHeight);"
        )
        total_width = driver.execute_script(
            "return Math.max(document.body.scrollWidth, "
            "document.documentElement.scrollWidth);"
        )
        driver.set_window_size(max(total_width, 1280), total_height + 100)
        time.sleep(0.5)  # let layout settle after resize
        driver.save_screenshot(str(out_path))
        print("second case")
        return True
    except Exception as e:
        print(f"[ERROR] Fallback screenshot also failed: {e}", file=sys.stderr)
        return False


def screenshot_career_pages(urls: list[str], output_dir: Path) -> dict[str, Path]:
    """
    Visits each URL in one persistent Chrome window, takes a full-page
    screenshot of each, and returns {url: screenshot_path} for successful
    captures only (failures are logged and skipped).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    driver = build_driver()
    results = {}

    try:
        for i, url in enumerate(urls):
            print(f"[INFO] ({i + 1}/{len(urls)}) Loading {url}")
            try:
                driver.get(url)
            except WebDriverException as e:
                print(f"[WARN] Failed to load {url}: {e}", file=sys.stderr)
                continue

            time.sleep(PAGE_LOAD_WAIT_SECONDS)

            screenshot_path = output_dir / f"page_{i:03d}.png"
            ok = capture_full_page_screenshot(driver, screenshot_path)
            if ok:
                results[url] = screenshot_path
                print(f"[INFO] Saved screenshot -> {screenshot_path}")
            else:
                print(f"[WARN] No screenshot captured for {url}", file=sys.stderr)
    finally:
        driver.quit()

    return results
