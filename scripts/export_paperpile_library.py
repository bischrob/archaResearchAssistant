#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

APP_URL = "https://app.paperpile.com"
DATA_AND_FILES_URL = "https://app.paperpile.com/settings/data-and-files"

LOGIN_HINT_SELECTORS = [
    "button:has-text('Sign in')",
    "button:has-text('Continue with Google')",
    "a:has-text('Sign in')",
]

EXPORT_TRIGGER_SELECTORS = [
    "button:has-text('Export data')",
    "button:has-text('Export')",
    "[role='button']:has-text('Export data')",
    "[role='button']:has-text('Export')",
]

JSON_FORMAT_SELECTORS = [
    "[role='menuitem']:has-text('JSON')",
    "button:has-text('JSON')",
    "[role='option']:has-text('JSON')",
    "label:has-text('JSON')",
    "text=/\\bJSON\\b/i",
]

DOWNLOAD_CONFIRM_SELECTORS = [
    "button:has-text('Download')",
    "button:has-text('Export')",
    "button:has-text('Save')",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Automate Paperpile JSON export using a persistent Chromium profile. "
            "First run usually requires manual Google sign-in in the opened browser."
        )
    )
    parser.add_argument(
        "--email",
        default="bischrob@gmail.com",
        help="Google account email hint (default: bischrob@gmail.com).",
    )
    parser.add_argument(
        "--output",
        default="Paperpile.json",
        help="Output JSON file path (default: Paperpile.json).",
    )
    parser.add_argument(
        "--profile-dir",
        default=".cache/paperpile-playwright-profile",
        help="Playwright persistent profile directory (default: .cache/paperpile-playwright-profile).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Timeout (seconds) for login and export waits (default: 300).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless (recommended only after initial login session is saved).",
    )
    parser.add_argument(
        "--browser-channel",
        choices=["chrome", "chromium", "msedge"],
        default="chrome",
        help=(
            "Browser channel for Playwright persistent context "
            "(default: chrome). Use chromium if Google login is not needed."
        ),
    )
    parser.add_argument(
        "--attach-cdp",
        action="store_true",
        help=(
            "Attach to an already-open Chromium/Chrome session over CDP instead of launching "
            "a Playwright-managed persistent browser."
        ),
    )
    parser.add_argument(
        "--cdp-url",
        default="http://127.0.0.1:9222",
        help="CDP endpoint URL when using --attach-cdp (default: http://127.0.0.1:9222).",
    )
    parser.add_argument(
        "--manual-only",
        action="store_true",
        help="Skip auto-clicks and wait for manual export interaction while capturing the download.",
    )
    return parser.parse_args()


def log(msg: str) -> None:
    print(f"[paperpile-export] {msg}")


def load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        raise SystemExit(
            "Missing dependency: playwright\n"
            "Install with:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )
    return sync_playwright


def click_first_visible(page, selectors: list[str], timeout_ms: int = 1200) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            continue
        if count == 0:
            continue
        target = locator.first
        try:
            if not target.is_visible(timeout=timeout_ms):
                continue
            target.scroll_into_view_if_needed(timeout=timeout_ms)
            target.click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def any_visible(page, selectors: list[str], timeout_ms: int = 300) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count() == 0:
                continue
            if locator.first.is_visible(timeout=timeout_ms):
                return True
        except Exception:
            continue
    return False


def maybe_fill_google_email(page, email: str) -> None:
    if "accounts.google.com" not in page.url:
        return
    try:
        email_input = page.locator("input[type='email']").first
        if email_input.count() == 0:
            return
        current = email_input.input_value(timeout=1000).strip()
        if current:
            return
        email_input.fill(email, timeout=2000)
        page.keyboard.press("Enter")
        log(f"Prefilled Google email: {email}")
    except Exception:
        pass


def wait_for_export_surface(page, timeout_ms: int, email_hint: str) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_navigate = 0.0
    prompted_login = False
    while time.monotonic() < deadline:
        url = page.url.lower()
        if "accounts.google.com" in url:
            maybe_fill_google_email(page, email_hint)
            if not prompted_login:
                log("Complete Google sign-in in the browser window (password/2FA/captcha).")
                prompted_login = True
        else:
            # Export surface is considered ready only when an export trigger is visible.
            if any_visible(page, EXPORT_TRIGGER_SELECTORS, timeout_ms=300):
                return True

            # Nudge sign-in buttons if present.
            click_first_visible(page, LOGIN_HINT_SELECTORS, timeout_ms=300)

            # Periodically steer browser toward the known export settings route.
            now = time.monotonic()
            if now - last_navigate > 3:
                try:
                    page.goto(DATA_AND_FILES_URL, wait_until="domcontentloaded", timeout=6000)
                    last_navigate = now
                except Exception:
                    pass

        page.wait_for_timeout(500)
    return False


def attach_capture_handlers(context, page):
    state = {"download": None, "json_candidates": []}

    def on_download(download):
        if state["download"] is None:
            state["download"] = download
            log(f"Download detected: {download.suggested_filename}")

    def on_response(response):
        url = response.url.lower()
        if not any(token in url for token in ("export", "download", "data-and-files", "references", "library")):
            return
        ctype = (response.headers.get("content-type") or "").lower()
        if "json" not in ctype and "text/plain" not in ctype:
            return
        try:
            body = response.text()
        except Exception:
            return
        payload = body.strip()
        if len(payload) < 500:
            return
        if not payload.startswith("[") and not payload.startswith("{"):
            return
        state["json_candidates"].append((len(payload), response.url, payload))

    context.on("download", on_download)
    page.on("response", on_response)
    return state


def wait_for_download(state, timeout_ms: int):
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        if state["download"] is not None:
            return state["download"]
        time.sleep(0.25)
    return None


def try_extract_json_candidate(state) -> str | None:
    candidates = sorted(state["json_candidates"], key=lambda x: x[0], reverse=True)
    for _size, _url, payload in candidates:
        try:
            parsed = json.loads(payload)
        except Exception:
            continue
        if isinstance(parsed, (list, dict)):
            return json.dumps(parsed, ensure_ascii=False, indent=2)
    return None


def run_auto_export_flow(page) -> None:
    # Directly open Data and Files where full library export lives.
    page.goto(DATA_AND_FILES_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    if click_first_visible(page, EXPORT_TRIGGER_SELECTORS, timeout_ms=2000):
        page.wait_for_timeout(700)
        click_first_visible(page, JSON_FORMAT_SELECTORS, timeout_ms=1400)
        page.wait_for_timeout(500)
        click_first_visible(page, DOWNLOAD_CONFIRM_SELECTORS, timeout_ms=1400)


def save_download(download, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    download.save_as(str(output_path))
    log(f"Saved download to: {output_path.resolve()}")


def validate_json_file(path: Path) -> None:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        raise SystemExit(f"Export file is not valid JSON: {path} ({exc})")

    if isinstance(payload, list):
        log(f"JSON validated. Top-level type=list, records={len(payload)}")
    else:
        log(f"JSON validated. Top-level type={type(payload).__name__}")


def main() -> None:
    args = parse_args()
    sync_playwright = load_playwright()

    output_path = Path(args.output).expanduser().resolve()
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    timeout_ms = max(args.timeout_seconds, 10) * 1000

    with sync_playwright() as p:
        browser = None
        context = None
        page = None
        created_page = False
        managed_context = False

        if args.attach_cdp:
            probe_url = args.cdp_url.rstrip("/") + "/json/version"
            try:
                with urllib.request.urlopen(probe_url, timeout=3) as resp:
                    if resp.status != 200:
                        raise SystemExit(
                            f"CDP endpoint probe failed: {probe_url} returned HTTP {resp.status}. "
                            "Make sure Chrome is running with --remote-debugging-port."
                        )
            except urllib.error.URLError as exc:
                raise SystemExit(
                    f"CDP endpoint not reachable: {probe_url}\n"
                    f"Error: {exc}\n"
                    "Start Chrome with remote debugging enabled, then re-run."
                )

            try:
                browser = p.chromium.connect_over_cdp(args.cdp_url)
            except Exception as exc:
                raise SystemExit(
                    f"Could not connect to CDP endpoint: {args.cdp_url}\n"
                    f"Error: {exc}\n"
                    "Start Chrome with remote debugging enabled, then re-run."
                )
            if not browser.contexts:
                browser.close()
                raise SystemExit(
                    "Connected to CDP but no browser contexts are available. "
                    "Open at least one Chrome window/tab first."
                )
            context = browser.contexts[0]
            try:
                page = context.new_page()
                created_page = True
            except Exception:
                page = context.pages[0] if context.pages else None
            if page is None:
                browser.close()
                raise SystemExit("Could not obtain a usable page from the CDP browser context.")
            log(f"Attached to Chrome via CDP: {args.cdp_url}")
        else:
            launch_kwargs = dict(
                user_data_dir=str(profile_dir),
                headless=args.headless,
                accept_downloads=True,
                viewport={"width": 1440, "height": 1024},
                channel=args.browser_channel,
            )
            try:
                context = p.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as exc:
                if args.browser_channel != "chromium":
                    log(
                        f"Failed to launch channel '{args.browser_channel}' ({exc}). "
                        "Falling back to bundled Chromium."
                    )
                    launch_kwargs["channel"] = "chromium"
                    context = p.chromium.launch_persistent_context(**launch_kwargs)
                else:
                    raise
            page = context.pages[0] if context.pages else context.new_page()
            managed_context = True

        state = attach_capture_handlers(context, page)

        try:
            page.goto(DATA_AND_FILES_URL, wait_until="domcontentloaded")
        except Exception:
            try:
                page.goto(APP_URL, wait_until="domcontentloaded")
            except Exception:
                pass

        export_surface_ready = wait_for_export_surface(page, timeout_ms=timeout_ms, email_hint=args.email)
        if export_surface_ready:
            log("Paperpile export surface detected.")
        else:
            log(
                "Export surface not auto-detected within timeout. "
                "You can still complete login/export manually while capture remains active."
            )

        if not args.manual_only:
            log("Attempting automatic export clicks on Settings > Data and files.")
            try:
                run_auto_export_flow(page)
            except Exception:
                pass

        if state["download"] is None:
            log(
                "If export did not start automatically, trigger it manually now:\n"
                "Profile menu (top-right) > Settings > Data and files > Export data > JSON."
            )

        download = wait_for_download(state, timeout_ms=timeout_ms)
        if download is not None:
            save_download(download, output_path)
            if managed_context:
                context.close()
            else:
                if created_page:
                    try:
                        page.close()
                    except Exception:
                        pass
                if browser is not None:
                    browser.close()
            validate_json_file(output_path)
            return

        json_payload = try_extract_json_candidate(state)
        if json_payload:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json_payload + "\n", encoding="utf-8")
            if managed_context:
                context.close()
            else:
                if created_page:
                    try:
                        page.close()
                    except Exception:
                        pass
                if browser is not None:
                    browser.close()
            log(f"Saved captured JSON response to: {output_path}")
            validate_json_file(output_path)
            return

        if managed_context:
            context.close()
        else:
            if created_page:
                try:
                    page.close()
                except Exception:
                    pass
            if browser is not None:
                browser.close()
        raise SystemExit(
            "No JSON export captured. Opened session and waited, but no download/JSON response appeared.\n"
            "Re-run and complete export manually in the browser window while the script is running."
        )


if __name__ == "__main__":
    main()
