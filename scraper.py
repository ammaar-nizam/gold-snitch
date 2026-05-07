import httpx
from bs4 import BeautifulSoup
import json
import os
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# Config — all values come from environment variables (GitHub Secrets in CI,
# or a local .env file during development).
# ---------------------------------------------------------------------------
TARGET_URL = os.environ["TARGET_URL"]
CSS_SELECTOR = os.environ["CSS_SELECTOR"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = Path("state.json")


def fetch_price() -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    try:
        r = httpx.get(TARGET_URL, headers=headers, timeout=15, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"HTTP fetch failed: {e}") from e

    soup = BeautifulSoup(r.text, "lxml")
    el = soup.select_one(CSS_SELECTOR)

    if el is None:
        raise ValueError(
            f"CSS selector '{CSS_SELECTOR}' matched nothing. "
            "The page structure may have changed."
        )

    return el.get_text(strip=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def notify(message: str, title: str = "Gold Price Alert", priority: str = "high") -> None:
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "moneybag",
            },
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[OK] Notification sent: {message}")
    except Exception as e:
        # Notification failure is non-fatal for state persistence but worth logging.
        print(f"[WARN] Notification failed: {e}")


def main() -> None:
    print(f"[INFO] Fetching: {TARGET_URL}")
    current_price = fetch_price()
    print(f"[INFO] Current price: {current_price}")

    state = load_state()
    previous_price = state.get("last_value")

    if previous_price is None:
        print("[INFO] No previous state — storing initial value.")
        notify(
            f"Gold price monitoring started.\nCurrent price: {current_price}",
            title="Gold Snitch — Started",
            priority="default",
        )
    elif current_price != previous_price:
        print(f"[CHANGE] {previous_price} → {current_price}")
        notify(
            f"Gold price changed!\n\nBefore: {previous_price}\nAfter:  {current_price}\n\n{TARGET_URL}",
            title="Gold Snitch — Price Changed",
            priority="high",
        )
    else:
        print(f"[INFO] No change: {current_price}")

    state["last_value"] = current_price
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        notify(
            f"Scraper encountered an error and stopped.\n\nError: {e}",
            title="Gold Snitch — ERROR",
            priority="urgent",
        )
        raise
