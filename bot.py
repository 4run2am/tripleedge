"""
TripleEdge — Telegram Bot Command Handler
==========================================
Handles incoming commands from users:
  /start        — register user
  /status       — on-demand signal
  /setportfolio — set personal portfolio value
  /help         — command list

Run via GitHub Actions on a polling schedule,
or locally for testing.
"""

import os
import json
import time
import requests
from signal import fetch_data, compute_signal, format_message, load_users, save_users, send_telegram

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}"


def get_updates(offset=None):
    params = {"timeout": 30, "offset": offset}
    resp   = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=35)
    return resp.json().get("result", [])


def handle_command(chat_id, text, first_name):
    users = load_users()
    text  = text.strip()

    # Auto-register user on any message
    if str(chat_id) not in users:
        users[str(chat_id)] = {"first_name": first_name, "portfolio_value": None}
        save_users(users)

    if text.startswith("/start"):
        msg = (
            f"👋 Welcome to *TripleEdge*, {first_name}!\n\n"
            f"I send weekly TQQQ trend signals every Monday morning.\n\n"
            f"*Commands:*\n"
            f"  /status — get current signal now\n"
            f"  /setportfolio 10000 — set your starting capital\n"
            f"  /help — show all commands\n\n"
            f"_You're now registered for Monday signals._\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"_TripleEdge — TQQQ Trend System_"
        )
        send_telegram(BOT_TOKEN, chat_id, msg)

    elif text.startswith("/status"):
        send_telegram(BOT_TOKEN, chat_id, "⏳ Fetching latest market data...")
        try:
            qqq, tqqq, vix      = fetch_data()
            sig                 = compute_signal(qqq, tqqq, vix)
            portfolio_value     = users.get(str(chat_id), {}).get("portfolio_value")
            msg                 = format_message(sig, portfolio_value=portfolio_value, mode="status")
            send_telegram(BOT_TOKEN, chat_id, msg)
        except Exception as e:
            send_telegram(BOT_TOKEN, chat_id, f"❌ Error fetching data: {e}")

    elif text.startswith("/setportfolio"):
        parts = text.split()
        if len(parts) < 2:
            send_telegram(BOT_TOKEN, chat_id,
                "Usage: `/setportfolio 10000`\nEnter your starting portfolio value in USD.")
        else:
            try:
                amount = float(parts[1].replace(",", "").replace("$", ""))
                users[str(chat_id)]["portfolio_value"] = amount
                save_users(users)
                send_telegram(BOT_TOKEN, chat_id,
                    f"✅ Portfolio set to `${amount:,.0f}`\n"
                    f"This will be used in your weekly signals and /status readouts.")
            except ValueError:
                send_telegram(BOT_TOKEN, chat_id,
                    "❌ Invalid amount. Usage: `/setportfolio 10000`")

    elif text.startswith("/help"):
        msg = (
            "*TripleEdge Commands*\n\n"
            "  /start — register and get started\n"
            "  /status — get the current signal right now\n"
            "  /setportfolio <amount> — set your starting capital\n"
            "  /help — show this message\n\n"
            "*How it works:*\n"
            "Every Monday I check:\n"
            "  • Is QQQ above its 200-week SMA? (regime)\n"
            "  • Is TQQQ above its 20-week SMA? (re-entry)\n"
            "  • Has TQQQ dropped 12% from its peak? (stop)\n\n"
            "Signal can be: 🟢 HOLD · 🔵 BUY · 🚨 SELL · ⚪️ CASH · 🟡 WAIT\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "_TripleEdge — TQQQ Trend System_"
        )
        send_telegram(BOT_TOKEN, chat_id, msg)

    else:
        send_telegram(BOT_TOKEN, chat_id,
            "I didn't recognize that command. Type /help to see what I can do.")


def run_bot():
    """Poll for updates and handle commands."""
    print("TripleEdge bot is running...")
    offset = None
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                msg    = update.get("message", {})
                if not msg:
                    continue
                chat_id    = msg["chat"]["id"]
                text       = msg.get("text", "")
                first_name = msg.get("from", {}).get("first_name", "there")
                if text:
                    handle_command(chat_id, text, first_name)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
