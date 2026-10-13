"""Screenshot the live dashboard for each ticket, exactly as it currently appears.

Requires the backend (port 8000) and dashboard (port 5173) to be running.
Uses the installed Google Chrome through Playwright (no browser download).

Run from hw5:  .venv/bin/python scripts/capture_board.py
Writes output/screenshots/ticket_<id>.png
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARD = "http://localhost:5173"
OUT = Path(__file__).resolve().parent.parent / "output" / "screenshots"
TICKETS = [101, 102, 103]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.goto(DASHBOARD)
        page.wait_for_selector(".ticket-card")
        page.wait_for_function("document.querySelector('.cash-balance')?.innerText.includes('$')")
        for tid in TICKETS:
            page.locator(".ticket-card", has_text=f"#{tid}").click()
            page.wait_for_function(f"document.querySelector('.panel .eyebrow')?.innerText.includes('#{tid}')")
            # wait for the run summary (or the empty state) to finish loading
            page.wait_for_function(
                "!document.body.innerText.includes('Loading summary') && "
                "(document.querySelector('.summary .agent-card') || document.querySelector('.empty.big'))"
            )
            page.wait_for_timeout(500)
            path = OUT / f"ticket_{tid}.png"
            page.screenshot(path=str(path), full_page=True)
            print(f"saved {path.relative_to(OUT.parent.parent)}")
        browser.close()


if __name__ == "__main__":
    main()
