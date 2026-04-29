"""
TripleEdge — Bot Actions Handler for GitHub Actions
=====================================================
Non-infinite polling version — runs for ~50 seconds then exits.
GitHub Actions calls this every 10 minutes via bot.yml.
Handles: /start, /status, /setportfolio, /help
"""

import os
import json
import time
import requests
from signal import fetch_data, compute_signal, format_message, load_users, save_users, send_telegram

BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN")
BASE_URL    = f"https://api.telegram.org/bot{BOT_TOKEN}"
OFFSET_FILE = "bot_offset.json"


def get_offset():
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset")
    return None


def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)


def get_updates(offset=None):
    params = {"timeout": 5, "offset": offset}
    try:
        resp = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=10)
        return resp.json().get("result", [])
    except Exception:
        return []


def handle_command(chat_id, text, first_name):
    users = load_users()
    text  = text.strip()

    if str(chat_id) not in users:
        users[str(chat_id)] = {"first_name": first_name, "portfolio_value": None}
        save_users(users)

    if text.startswith("/start"):
        msg = (
            f"👋 Welcome to *TripleEdge*, {first_name}\\!\n\n"
            f"I send weekly signals every Monday morning for two engines:\n"
            f"  📈 *UPRO* \\(75%\\) — 3x S&P 500\n"
            f"  🥇 *UGL* \\(25%\\) — 2x Gold\n\n"
            f"*Commands:*\n"
            f"  /status — get current signals now\n"
            f"  /setportfolio 10000 — set your portfolio value\n"
            f"  /help — show all commands\n\n"
            f"_You're now registered for Monday signals\\._\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"_TripleEdge · UPRO \\+ UGL · Not financial advice_"
        )
        send_telegram(BOT_TOKEN, chat_id, msg)

    elif text.startswith("/status"):
        send_telegram(BOT_TOKEN, chat_id, "⏳ Fetching latest market data\\.\\.\\.")
        try:
            spy, upro, gld, ugl = fetch_data()
            sig                 = compute_signal(spy, upro, gld, ugl)
            portfolio_value     = users.get(str(chat_id), {}).get("portfolio_value")
            msg                 = format_message(sig, portfolio_value=portfolio_value, mode="status")
            send_telegram(BOT_TOKEN, chat_id, msg)
        except Exception as e:
            send_telegram(BOT_TOKEN, chat_id, f"❌ Error fetching data: {e}")

    elif text.startswith("/setportfolio"):
        parts = text.split()
        if len(parts) < 2:
            send_telegram(BOT_TOKEN, chat_id,
                "Usage: `/setportfolio 10000`\nEnter your total portfolio value in USD\\.")
        else:
            try:
                amount = float(parts[1].replace(",", "").replace("$", ""))
                users[str(chat_id)]["portfolio_value"] = amount
                save_users(users)
                send_telegram(BOT_TOKEN, chat_id,
                    f"✅ Portfolio set to `${amount:,.0f}`\n"
                    f"  UPRO 75%: `${amount * 0.75:,.0f}`\n"
                    f"  UGL  25%: `${amount * 0.25:,.0f}`\n"
                    f"_Shown in your weekly signals and /status readouts\\._")
            except ValueError:
                send_telegram(BOT_TOKEN, chat_id,
                    "❌ Invalid amount\\. Usage: `/setportfolio 10000`")

    elif text.startswith("/help"):
        msg = (
            "*TripleEdge Commands*\n\n"
            "  /status — current signal for both engines\n"
            "  /setportfolio <amount> — set your portfolio value\n"
            "  /help — show this message\n\n"
            "*Strategy \\(75% UPRO / 25% UGL\\):*\n\n"
            "*UPRO Engine*\n"
            "  • SPY above 65\\-week SMA? \\(regime\\)\n"
            "  • UPRO above 10\\-week SMA? \\(re\\-entry\\)\n"
            "  • UPRO within 22% of peak? \\(trailing stop\\)\n\n"
            "*UGL Engine*\n"
            "  • GLD above 100\\-week SMA? \\(regime\\)\n"
            "  • GLD above 20\\-week SMA? \\(re\\-entry\\)\n"
            "  • UGL within 28% of peak? \\(trailing stop\\)\n\n"
            "Signal: 🟢 HOLD · 🟡 WAIT · ⚪️ CASH · 🚨 SELL\n"
            "Cash goes to SGOV while sidelined \\(\\~5\\.2% yield\\)\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "_TripleEdge · UPRO \\+ UGL · Not financial advice_"
        )
        send_telegram(BOT_TOKEN, chat_id, msg)

    else:
        send_telegram(BOT_TOKEN, chat_id,
            "I didn't recognize that command\\. Type /help to see what I can do\\.")


def main():
    print("TripleEdge bot polling...")
    offset    = get_offset()
    start     = time.time()
    processed = 0

    while time.time() - start < 50:
        updates = get_updates(offset)
        for update in updates:
            offset     = update["update_id"] + 1
            msg        = update.get("message", {})
            if not msg:
                continue
            chat_id    = msg["chat"]["id"]
            text       = msg.get("text", "")
            first_name = msg.get("from", {}).get("first_name", "there")
            if text:
                print(f"  [{chat_id}] {text}")
                handle_command(chat_id, text, first_name)
                processed += 1

        save_offset(offset)
        time.sleep(2)

    print(f"Done. Processed {processed} message(s).")


if __name__ == "__main__":
    main()
