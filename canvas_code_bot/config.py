from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    discord_token: str
    canvas_token: str
    canvas_base_url: str
    app_mode: str
    admin_discord_id: int
    db_url: str
    code_length: int
    oneshot_late_guard_hours: int

    @classmethod
    def from_env(cls) -> AppConfig:
        app_mode = os.environ.get("APP_MODE", "development").lower()
        if app_mode == "production":
            canvas_base_url = _require("CANVAS_BASE_URL_PROD")
        else:
            canvas_base_url = _require("CANVAS_BASE_URL_DEV")

        return cls(
            discord_token=_require("DISCORD_TOKEN"),
            canvas_token=_require("CANVAS_TOKEN"),
            canvas_base_url=canvas_base_url,
            app_mode=app_mode,
            admin_discord_id=int(_require("ADMIN_DISCORD_ID")),
            db_url=os.environ.get("DB_URL", "sqlite:///quizbot.db"),
            code_length=int(os.environ.get("CODE_LENGTH", "6")),
            oneshot_late_guard_hours=int(
                os.environ.get("ONESHOT_LATE_GUARD_HOURS", "24")
            ),
        )


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable {name!r} is not set or is empty."
        )
    return value
