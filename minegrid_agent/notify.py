"""Discord alerts. The webhook comes ONLY from the DISCORD_WEBHOOK_URL environment variable."""

from __future__ import annotations

import logging
import os
import time

from .http import post_json

log = logging.getLogger("minegrid.notify")

GREEN, RED, BLUE = 5763719, 15548997, 3447003


class Notifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self.url = (webhook_url if webhook_url is not None else os.environ.get("DISCORD_WEBHOOK_URL", "")).strip()

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def send(self, title: str, description: str, color: int, fields: list[dict] | None = None) -> None:
        if not self.enabled:
            log.info("[notify disabled] %s | %s", title, description.replace("\n", " "))
            return
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields or [],
            "footer": {"text": "MineGrid Agent • paper trading"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            post_json(self.url, {"embeds": [embed]})
        except Exception as exc:  # never crash the agent because of Discord
            log.error("Discord send failed: %s", exc)


def field(name: str, value: str, inline: bool = True) -> dict:
    return {"name": name, "value": value, "inline": inline}
