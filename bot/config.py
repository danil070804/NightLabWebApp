from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    bot_token: str
    db_path: str
    admin_ids: list[int]
    support_text: str
    merchant_chat_id: int | None = None

    # Fallback defaults (now stored in DB, but keep for compatibility)
    channel_id: int | str | None = None
    channel_url: str = "https://t.me/your_channel"
    team_url: str = "https://t.me/your_team"
    rules_url: str = "https://t.me/your_channel/1"
    welcome_photo_url: str | None = None


def load_config() -> Config:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required in .env")

    db_path = os.getenv("DB_PATH", "./data.db").strip()

    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    admin_ids = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()]

    support_text = os.getenv("SUPPORT_TEXT", "Напишите в поддержку.").strip()

    mch = os.getenv("MERCHANT_CHAT_ID", "").strip()
    merchant_chat_id = int(mch) if mch.lstrip("-").isdigit() else None

    channel_id_raw = os.getenv("CHANNEL_ID", "").strip()
    channel_id = int(channel_id_raw) if channel_id_raw.lstrip("-").isdigit() else (channel_id_raw or None)

    return Config(
        bot_token=bot_token,
        db_path=db_path,
        admin_ids=admin_ids,
        support_text=support_text,
        merchant_chat_id=merchant_chat_id,
        channel_id=channel_id,
        channel_url=os.getenv("CHANNEL_URL", "https://t.me/your_channel").strip(),
        team_url=os.getenv("TEAM_URL", "https://t.me/your_team").strip(),
        rules_url=os.getenv("RULES_URL", "https://t.me/your_channel/1").strip(),
        welcome_photo_url=os.getenv("WELCOME_PHOTO_URL", "").strip() or None,
    )
