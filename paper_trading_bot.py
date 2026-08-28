"""
Paper Trading Bot — Crypto (starting point)

What this does, in plain terms:
- Checks a coin's price
- Compares a short-term average price to a longer-term average price
- "Buys" with pretend money when the short-term trend rises above the long-term trend
- "Sells" when it drops back below
- Keeps a running account balance in state.json, and a full history in trades.csv

This script can run two ways:
  1. Non-stop on a server you leave running:   python paper_trading_bot.py
  2. Once per scheduled run (e.g. a free GitHub Actions cron job):
     python paper_trading_bot.py --once

No external libraries needed — just plain Python.
"""

import json
import csv
import time
import argparse
import os
from datetime import datetime, timezone
import urllib.request
import urllib.error

# ---------- Settings you can tweak ----------
COIN_ID = "bitcoin"          # CoinGecko id, e.g. "bitcoin", "ethereum"
SHORT_WINDOW = 5             # how many recent checks make up the "short-term" average
LONG_WINDOW = 15             # how many recent checks make up the "long-term" average
STARTING_CASH = 10000.0      # pretend starting money
POLL_SECONDS = 60            # how often to check price when running non-stop
STATE_FILE = "state.json"
TRADES_FILE = "trades.csv"
# ---------------------------------------------


def fetch_price(coin_id):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return float(data[coin_id]["usd"])
    except (urllib.error.URLError, KeyError, ValueError) as e:
        print(f"[warn] price fetch failed ({e}); skipping this check")
        return None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "cash": STARTING_CASH,
        "coins_held": 0.0,
        "in_position": False,
        "price_history": [],
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def log_trade(action, price, value):
    is_new = not os.path.exists(TRADES_FILE)
    with open(TRADES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "action", "price", "value"])
        writer.writerow([datetime.now(timezone.utc).isoformat(), action, price, value])


def average(values):
    return sum(values) / len(values)


def run_one_check(state):
    price = fetch_price(COIN_ID)
    if price is None:
        return state

    state["price_history"].append(price)
    state["price_history"] = state["price_history"][-max(LONG_WINDOW, 60):]

    history = state["price_history"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if len(history) < LONG_WINDOW:
        print(f"{now_str}  price=${price:,.2f}  (still gathering history: {len(history)}/{LONG_WINDOW})")
        save_state(state)
        return state

    short_ma = average(history[-SHORT_WINDOW:])
    long_ma = average(history[-LONG_WINDOW:])
    portfolio_value = state["cash"] + state["coins_held"] * price

    print(
        f"{now_str}  price=${price:,.2f}  short_avg=${short_ma:,.2f}  "
        f"long_avg=${long_ma:,.2f}  portfolio=${portfolio_value:,.2f}"
    )

    if not state["in_position"] and short_ma > long_ma and state["cash"] > 0:
        bought = state["cash"] / price
        spent = state["cash"]
        state["coins_held"] = bought
        state["cash"] = 0.0
        state["in_position"] = True
        log_trade("BUY", price, spent)
        print(f"  -> BUY: spent ${spent:,.2f}, now holding {bought:.6f} {COIN_ID}")

    elif state["in_position"] and short_ma < long_ma:
        proceeds = state["coins_held"] * price
        state["cash"] = proceeds
        state["coins_held"] = 0.0
        state["in_position"] = False
        log_trade("SELL", price, proceeds)
        print(f"  -> SELL: received ${proceeds:,.2f}")

    save_state(state)
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="check price once and exit (for scheduled/cron use)")
    args = parser.parse_args()

    state = load_state()

    if args.once:
        run_one_check(state)
        return

    print(f"Starting continuous paper trading bot for {COIN_ID}. Checking every {POLL_SECONDS}s.")
    while True:
        state = run_one_check(state)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
