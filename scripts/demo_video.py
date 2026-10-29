"""Playwright demo video script -- runs the Keystone UI in replay mode.

Records a screen capture demonstrating:
1. Persona switching (CEO, Contractor, HR Manager, Sales Rep)
2. Permission enforcement (salary query blocked for contractor)
3. Compare view (v0 vs v4 side-by-side)

Prerequisites:
  pip install playwright
  playwright install chromium

Usage:
  # Start the UI dev server first:
  cd ui-web && npm run dev

  # Then run the demo (records to demo_output/):
  python scripts/demo_video.py

  # Or with a custom base URL:
  python scripts/demo_video.py --url http://localhost:5173

The script uses pre-recorded fixtures from ui-web/public/fixtures/ so it
does NOT require a running backend, database, or LLM. Only the Vite dev
server (or any static server for ui-web/dist/) is needed.
"""

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("demo_output")
BASE_URL = "http://localhost:5173"

# Personas to cycle through (must match the UI's people rail)
PERSONAS = [
    {"name": "Danielle Johnson", "role": "CEO", "id": 1},
    {"name": "John Wheeler", "role": "HR Business Partner", "id": 5},
    {"name": "Jose Richards", "role": "Operations Manager", "id": 9},
    {"name": "Michelle Rasmussen", "role": "Contractor", "id": 15},
]

# Scenarios to demonstrate
SCENARIOS = [
    {
        "label": "salary_own",
        "message": "What is my salary?",
        "description": "Each persona asks for their own salary",
    },
    {
        "label": "salary_other",
        "message": "Show me the salary for employee 44",
        "description": "Attempt to see another employee's salary (blocked for non-HR)",
    },
    {
        "label": "deal_search",
        "message": "What open deals does the Sales team have?",
        "description": "CRM access varies by role",
    },
]


def wait_for_response(page, timeout_ms=10000):
    """Wait for the chat response to finish streaming."""
    # Wait for the streaming indicator to appear then disappear
    try:
        page.wait_for_selector(".message.assistant", timeout=timeout_ms)
        # Wait for streaming to complete (no more pending indicator)
        page.wait_for_function(
            "() => !document.querySelector('.streaming-indicator')",
            timeout=timeout_ms,
        )
    except Exception:
        # In replay mode, responses are instant
        pass
    time.sleep(0.5)  # Brief pause for visual clarity


def screenshot(page, name):
    """Take a screenshot and save to output directory."""
    path = OUTPUT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  Screenshot: {path}")


def select_persona(page, persona):
    """Click a persona in the people rail."""
    # The people rail shows persona cards with names
    card = page.locator(f"text={persona['name']}").first
    if card.is_visible():
        card.click()
        time.sleep(0.3)
    else:
        # Try clicking by role if name isn't visible
        card = page.locator(f"text={persona['role']}").first
        card.click()
        time.sleep(0.3)


def send_message(page, message):
    """Type and send a message in the chat input."""
    input_box = page.locator("textarea, input[type='text']").first
    input_box.fill(message)
    # Press Enter or click Send
    input_box.press("Enter")


def demo_persona_switching(page):
    """Scene 1: Switch between personas, show the people rail."""
    print("\n--- Scene 1: Persona Switching ---")
    screenshot(page, "01_initial_load")

    for i, persona in enumerate(PERSONAS):
        print(f"  Switching to {persona['name']} ({persona['role']})")
        select_persona(page, persona)
        time.sleep(0.5)
        screenshot(page, f"02_persona_{persona['role'].lower().replace(' ', '_')}")


def demo_permission_enforcement(page):
    """Scene 2: Show permission enforcement -- same query, different results."""
    print("\n--- Scene 2: Permission Enforcement ---")

    scenario = SCENARIOS[1]  # salary_other -- shows permission blocking

    for persona in [PERSONAS[0], PERSONAS[3]]:  # CEO vs Contractor
        select_persona(page, persona)
        time.sleep(0.3)

        send_message(page, scenario["message"])
        wait_for_response(page)

        screenshot(
            page,
            f"03_permission_{persona['role'].lower().replace(' ', '_')}_{scenario['label']}",
        )
        print(f"  {persona['role']}: sent '{scenario['message']}'")


def demo_compare_view(page):
    """Scene 3: Compare view showing v0 vs v4 side-by-side."""
    print("\n--- Scene 3: Compare View ---")

    # Click the Compare nav button
    compare_btn = page.locator("text=Compare").first
    if compare_btn.is_visible():
        compare_btn.click()
        time.sleep(1)
        screenshot(page, "04_compare_view")
        print("  Compare view opened")
    else:
        print("  Compare button not found -- skipping")


def demo_full_scenario(page):
    """Scene 4: Full scenario walkthrough with HR Manager."""
    print("\n--- Scene 4: Full Scenario ---")

    # Select HR Manager
    select_persona(page, PERSONAS[1])
    time.sleep(0.3)

    for scenario in SCENARIOS:
        send_message(page, scenario["message"])
        wait_for_response(page)
        screenshot(
            page,
            f"05_scenario_{scenario['label']}",
        )
        print(f"  HR Manager: {scenario['label']}")


def main():
    parser = argparse.ArgumentParser(description="Record Keystone demo video")
    parser.add_argument("--url", default=BASE_URL, help="UI base URL")
    parser.add_argument("--video", action="store_true", help="Record video (slower)")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Demo output: {OUTPUT_DIR.resolve()}")
    print(f"UI URL: {args.url}")

    with sync_playwright() as p:
        browser_args = {
            "headless": not args.headed,
        }

        context_args = {
            "viewport": {"width": 1440, "height": 900},
        }

        if args.video:
            context_args["record_video_dir"] = str(OUTPUT_DIR / "video")
            context_args["record_video_size"] = {"width": 1440, "height": 900}

        browser = p.chromium.launch(**browser_args)
        context = browser.new_context(**context_args)
        page = context.new_page()

        print(f"\nNavigating to {args.url}...")
        page.goto(args.url, wait_until="networkidle")
        time.sleep(1)

        # Enable replay mode via URL param if fixtures exist
        page.goto(f"{args.url}?mode=replay", wait_until="networkidle")
        time.sleep(1)

        demo_persona_switching(page)
        demo_permission_enforcement(page)
        demo_compare_view(page)
        demo_full_scenario(page)

        if args.video:
            video_path = page.video.path()
            print(f"\nVideo saved: {video_path}")

        context.close()
        browser.close()

    print(f"\nDone. Screenshots in {OUTPUT_DIR.resolve()}/")


if __name__ == "__main__":
    main()
