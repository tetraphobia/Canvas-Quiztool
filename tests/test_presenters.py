"""
Tests for bot/presenters.py — DiscordNotifier.

Uses a FakeBot / FakeChannel so no real Discord connection is needed.
The discord.Embed class is used directly (it has no I/O side-effects).
"""
from datetime import datetime

import discord
import pytest

from canvas_code_bot.bot.presenters import DiscordNotifier
from canvas_code_bot.core.models import Quiz

_NOW = datetime(2026, 8, 27, 12, 0, 0)


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeChannel:
    def __init__(self):
        self.messages: list[dict] = []

    async def send(self, content=None, embed=None):
        self.messages.append({"content": content, "embed": embed})


class FakeBot:
    def __init__(self, channel=None):
        self._channel = channel

    def get_channel(self, channel_id):
        return self._channel


def _quiz():
    return Quiz(
        id=1, course_id=10, assignment_id=100,
        course_name="CS101", quiz_name="Midterm",
        added_by=999, added_at=_NOW,
    )


# ── notify_success ─────────────────────────────────────────────────────────────

async def test_notify_success_sends_one_message():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    await notifier.notify_success(1, _quiz(), "ABC123")
    assert len(channel.messages) == 1


async def test_notify_success_sends_embed():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    await notifier.notify_success(1, _quiz(), "ABC123")
    assert isinstance(channel.messages[0]["embed"], discord.Embed)


async def test_notify_success_embed_contains_code():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    await notifier.notify_success(1, _quiz(), "XYZ999")
    embed = channel.messages[0]["embed"]
    fields_text = " ".join(f.value for f in embed.fields)
    assert "XYZ999" in fields_text


async def test_notify_success_no_channel_is_silent():
    notifier = DiscordNotifier(FakeBot(channel=None))
    # Must not raise even if the channel is not found
    await notifier.notify_success(999, _quiz(), "ABC123")


# ── notify_group_success ──────────────────────────────────────────────────────

async def test_notify_group_success_sends_one_message():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    q2 = Quiz(
        id=2, course_id=20, assignment_id=200,
        course_name="CS201", quiz_name="Final",
        added_by=999, added_at=_NOW,
    )
    await notifier.notify_group_success(1, [_quiz(), q2], "GRPCODE")
    assert len(channel.messages) == 1


async def test_notify_group_success_embed_contains_code():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    await notifier.notify_group_success(1, [_quiz()], "GRPXYZ")
    embed = channel.messages[0]["embed"]
    fields_text = " ".join(f.value for f in embed.fields)
    assert "GRPXYZ" in fields_text


async def test_notify_group_success_embed_lists_all_quizzes():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    q2 = Quiz(
        id=2, course_id=20, assignment_id=200,
        course_name="CS201", quiz_name="Final",
        added_by=999, added_at=_NOW,
    )
    await notifier.notify_group_success(1, [_quiz(), q2], "CODE")
    embed = channel.messages[0]["embed"]
    quizzes_field = next(f for f in embed.fields if f.name == "Quizzes")
    assert "Midterm" in quizzes_field.value
    assert "Final" in quizzes_field.value
    assert "(10)" in quizzes_field.value   # course_id of _quiz()
    assert "(20)" in quizzes_field.value   # course_id of q2


async def test_notify_group_success_no_channel_is_silent():
    notifier = DiscordNotifier(FakeBot(channel=None))
    await notifier.notify_group_success(999, [_quiz()], "CODE")


# ── notify_error ───────────────────────────────────────────────────────────────

async def test_notify_error_sends_one_message():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    await notifier.notify_error(1, _quiz(), "Canvas timeout", admin_id=42)
    assert len(channel.messages) == 1


async def test_notify_error_pings_admin_in_content():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    await notifier.notify_error(1, _quiz(), "Canvas timeout", admin_id=42)
    content = channel.messages[0]["content"] or ""
    assert "<@42>" in content


async def test_notify_error_sends_embed():
    channel = FakeChannel()
    notifier = DiscordNotifier(FakeBot(channel=channel))
    await notifier.notify_error(1, _quiz(), "Canvas timeout", admin_id=42)
    assert isinstance(channel.messages[0]["embed"], discord.Embed)


async def test_notify_error_no_channel_is_silent():
    notifier = DiscordNotifier(FakeBot(channel=None))
    await notifier.notify_error(999, _quiz(), "err", admin_id=42)
