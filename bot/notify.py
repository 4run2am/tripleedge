"""
Optional Telegram notification hook.

If TELEGRAM_BOT_TOKEN and BOT_NOTIFY_CHAT_ID are present in the environment,
sends a one-line summary on each run. If either is missing, silently no-ops.

Tokens are NEVER hardcoded — config.load_config() reads them from env.
"""

import requests

from .config import BotConfig


def notify(cfg: BotConfig, message: str) -> bool:
    """Send a Telegram message if both token + chat_id are configured.
    Returns True on success, False if notification was skipped or failed."""
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
        resp = requests.post(
            url,
            data={
                "chat_id":    cfg.telegram_chat_id,
                "text":       message,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        print(f"  notify: {e}")
        return False
