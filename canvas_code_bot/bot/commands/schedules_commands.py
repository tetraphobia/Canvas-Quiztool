from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands

from canvas_code_bot.core.exceptions import ScheduleConflictError
from canvas_code_bot.core.models import Schedule, ScheduleKind, ScheduleStatus
from canvas_code_bot.bot.commands.schedule_commands import (
    _DEFAULT_WINDOW_DAYS,
    _LOCAL_TZ,
    _TZ,
    _parse_dt,
    _parse_ids,
    _validate,
)

logger = logging.getLogger(__name__)


def _fmt_dt(dt: datetime) -> str:
    """Convert a stored naive-UTC datetime to Eastern time for display."""
    return dt.replace(tzinfo=timezone.utc).astimezone(_LOCAL_TZ).strftime("%Y-%m-%dT%H:%M ET")


class SchedulesGroup(app_commands.Group, name="schedules", description="Manage rotation schedules."):
    def __init__(self, services) -> None:
        super().__init__()
        self._svc = services

    @app_commands.command(name="help", description="Show usage for /qb schedules commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="/qb schedules — Schedule Management",
            description=(
                "Configure when the bot rotates access codes. "
                "Schedules are either **recurring** (cron) or **one-shot** (at)."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="`list [show_all]`",
            value=(
                "Show rotation schedules.\n"
                "Default: active schedules only (excludes expired and completed).\n"
                "• `show_all:True` — include expired and completed schedules."
            ),
            inline=False,
        )
        embed.add_field(
            name="`add quizids:<ids> [options]`",
            value=(
                "Add a schedule for one or more quizzes (comma-separated IDs).\n"
                "**Timing** — provide exactly one of:\n"
                "• `cron:<5-field crontab>` — recurring (e.g. `0 9 * * 1-5`)\n"
                "• `at:<ISO 8601 datetime>` — one-shot (e.g. `2026-09-01T09:00`)\n"
                "**Code** — provide exactly one of:\n"
                "• `random:True` *(default)* — generate a random 6-character code\n"
                "• `random:False code:<value>` — use a fixed code\n"
                "**Window** (recurring only, optional):\n"
                "• `start:<ISO 8601>` — when the window opens\n"
                "• `end:<ISO 8601>` — when the window closes (default: start + 2 weeks)"
            ),
            inline=False,
        )
        embed.add_field(
            name="`update schedule_id:<id> [options]`",
            value=(
                "Edit an existing schedule in place. "
                "Only the fields you provide are changed.\n"
                "Switching `cron` → `at` or vice-versa changes the schedule kind.\n"
                "Overlap conflicts are re-checked against other schedules for the same quiz."
            ),
            inline=False,
        )
        embed.add_field(
            name="`delete schedule_id:<id>`",
            value=(
                "Remove a schedule by its ID (shown in `list`).\n"
                "The quiz itself is kept; only this schedule is removed."
            ),
            inline=False,
        )
        embed.add_field(
            name="Examples",
            value=(
                "Rotate weekdays at 9 AM:\n"
                "`/qb schedules add quizids:1,2 cron:0 9 * * 1-5`\n\n"
                "One-shot on Sept 1 at 9 AM:\n"
                "`/qb schedules add quizids:3 at:2026-09-01T09:00`\n\n"
                "Fixed code on a recurring schedule:\n"
                "`/qb schedules add quizids:1 cron:0 9 * * * random:False code:EXAM01`\n\n"
                "Update schedule 5 to fire at 10 AM instead:\n"
                "`/qb schedules update schedule_id:5 cron:0 10 * * 1-5`"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="list", description="Show rotation schedules.")
    @app_commands.describe(
        show_all="Include expired and completed schedules (default: false).",
    )
    async def list_schedules(
        self, interaction: discord.Interaction, show_all: bool = False
    ) -> None:
        schedules = (
            self._svc.schedule_repo.list_all()
            if show_all
            else self._svc.schedule_repo.list_active()
        )
        if not schedules:
            label = "schedules" if show_all else "active schedules"
            await interaction.response.send_message(f"No {label} found.", ephemeral=True)
            return

        # Group by group_id so quizzes that fire together appear together.
        # Schedules without a group_id get an isolated key.
        groups: dict[str, list] = {}
        for s in schedules:
            key = s.group_id or f"_solo_{s.id}"
            groups.setdefault(key, []).append(s)

        embed = discord.Embed(
            title="All Schedules" if show_all else "Active Schedules",
            color=discord.Color.blurple(),
        )
        for group in groups.values():
            rep = group[0]  # all schedules in a group share the same timing

            quiz_lines = []
            for s in group:
                quiz = self._svc.quiz_repo.get(s.quiz_id)
                if quiz:
                    quiz_lines.append(f"({quiz.course_id}) {quiz.quiz_name}")
                else:
                    quiz_lines.append(f"(?) quiz {s.quiz_id}")

            timing: list[str] = []
            if rep.kind.value == "recurring":
                timing.append(f"cron: `{rep.cron}`")
                if rep.start_at:
                    timing.append(f"start: {_fmt_dt(rep.start_at)}")
                if rep.end_at:
                    timing.append(f"end: {_fmt_dt(rep.end_at)}")
            else:
                if rep.run_at:
                    timing.append(f"at: {_fmt_dt(rep.run_at)}")

            last = _fmt_dt(rep.last_fired_at) if rep.last_fired_at else "never"
            timing.append(f"last fired: {last}")

            status_tag = f" [{rep.status.value}]" if show_all else ""
            ids_str = ", ".join(str(s.id) for s in group)
            field_name = f"id={ids_str}{status_tag}"
            value = "\n".join(quiz_lines + [" · ".join(timing)])

            embed.add_field(name=field_name, value=value, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="add", description="Add a rotation schedule for one or more quizzes.")
    @app_commands.describe(
        quizids="Comma-separated quiz IDs.",
        random="Generate a random code each time (default: true).",
        code="Fixed code (only when random=false).",
        cron="5-field crontab for recurring (e.g. `0 9 * * 1-5`).",
        at="One-shot datetime in ISO 8601 (e.g. `2026-09-01T09:00`).",
        start="Recurring window start, e.g. 2026-09-01T09:00 (optional).",
        end="Recurring window end, e.g. 2026-12-31T23:59 (default: start + 2 weeks).",
    )
    async def add_schedule(
        self,
        interaction: discord.Interaction,
        quizids: str,
        random: bool = True,
        code: str | None = None,
        cron: str | None = None,
        at: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> None:
        error = _validate(random, code, cron, at)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            start_dt = _parse_dt(start) if start else None
            end_dt = _parse_dt(end) if end else None
            run_at_dt = _parse_dt(at) if at else None
        except ValueError as exc:
            await interaction.response.send_message(
                f"Invalid date/time: {exc}. Use ISO 8601 format, e.g. `2026-09-01T09:00`.",
                ephemeral=True,
            )
            return

        if cron and start_dt and end_dt is None:
            end_dt = start_dt + timedelta(days=_DEFAULT_WINDOW_DAYS)

        await interaction.response.defer(ephemeral=True)

        ids = _parse_ids(quizids)
        if not ids:
            await interaction.followup.send("No valid quiz IDs provided.", ephemeral=True)
            return

        kind = ScheduleKind.RECURRING if cron else ScheduleKind.ONESHOT
        group_id = str(uuid.uuid4())

        results = []
        for qid in ids:
            quiz = self._svc.quiz_repo.get(qid)
            if quiz is None:
                results.append(f"Quiz {qid}: not found.")
                continue

            proposed = Schedule(
                quiz_id=qid,
                kind=kind,
                group_id=group_id,
                timezone=_TZ,
                random=random,
                status=ScheduleStatus.ACTIVE,
                created_by=interaction.user.id,
                created_at=now_utc,
                cron=cron,
                run_at=run_at_dt,
                start_at=start_dt,
                end_at=end_dt,
                fixed_code=code if not random else None,
            )

            try:
                saved = self._svc.schedule_svc.add_schedule(proposed)
                results.append(f"**{quiz.quiz_name}**: schedule added (id={saved.id}).")
            except ScheduleConflictError as exc:
                ids_str = ", ".join(str(i) for i in exc.conflict_ids)
                results.append(
                    f"**{quiz.quiz_name}**: overlaps with existing schedule(s) "
                    f"{ids_str}. Delete them first with `/qb schedules delete <id>`."
                )
            except Exception as exc:
                logger.exception("schedules add failed for quiz %d", qid)
                results.append(f"**{quiz.quiz_name}**: error — {exc}.")

        await interaction.followup.send("\n".join(results), ephemeral=True)

    @app_commands.command(name="update", description="Update an existing schedule by ID.")
    @app_commands.describe(
        schedule_id="The schedule ID to update.",
        random="Generate a random code each time.",
        code="Fixed code to use (only when random=false).",
        cron="New 5-field crontab (switches schedule to RECURRING).",
        at="New one-shot datetime, e.g. 2026-09-01T09:00 (switches schedule to ONESHOT).",
        start="New window start, e.g. 2026-09-01T09:00.",
        end="New window end, e.g. 2026-12-31T23:59.",
    )
    async def update_schedule(
        self,
        interaction: discord.Interaction,
        schedule_id: int,
        random: bool | None = None,
        code: str | None = None,
        cron: str | None = None,
        at: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> None:
        sched = self._svc.schedule_repo.get(schedule_id)
        if sched is None:
            await interaction.response.send_message(
                f"Schedule {schedule_id} not found.", ephemeral=True
            )
            return

        if cron and at:
            await interaction.response.send_message(
                "Provide `cron` **or** `at`, not both.", ephemeral=True
            )
            return

        if random is not None or code is not None:
            err = _validate_update_code(
                random if random is not None else sched.random,
                code,
                provided_code=code is not None,
            )
            if err:
                await interaction.response.send_message(err, ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)

        try:
            new_start_dt = _parse_dt(start) if start is not None else sched.start_at
            new_end_dt = _parse_dt(end) if end is not None else sched.end_at
            new_run_at_dt = _parse_dt(at) if at is not None else sched.run_at
        except ValueError as exc:
            await interaction.followup.send(
                f"Invalid date/time: {exc}.", ephemeral=True
            )
            return

        if cron is not None:
            new_kind = ScheduleKind.RECURRING
            new_cron = cron
            new_run_at_dt = None
            if start is not None and end is None:
                new_end_dt = _parse_dt(start) + timedelta(days=_DEFAULT_WINDOW_DAYS)
        elif at is not None:
            new_kind = ScheduleKind.ONESHOT
            new_cron = None
            new_start_dt = None
            new_end_dt = None
        else:
            new_kind = sched.kind
            new_cron = sched.cron

        new_random = random if random is not None else sched.random
        if new_random:
            new_fixed_code = None
        elif code is not None:
            new_fixed_code = code
        else:
            new_fixed_code = sched.fixed_code

        updated = Schedule(
            id=sched.id,
            quiz_id=sched.quiz_id,
            kind=new_kind,
            group_id=sched.group_id,
            timezone=sched.timezone,
            random=new_random,
            fixed_code=new_fixed_code,
            code_length=sched.code_length,
            status=sched.status,
            created_by=sched.created_by,
            created_at=sched.created_at,
            cron=new_cron,
            run_at=new_run_at_dt,
            start_at=new_start_dt,
            end_at=new_end_dt,
            last_fired_at=sched.last_fired_at,
            next_fire_at=sched.next_fire_at,
        )

        timing_changed = any(x is not None for x in (cron, at, start, end))
        try:
            self._svc.schedule_svc.update_schedule(updated, timing_changed=timing_changed)
            await interaction.followup.send(
                f"Schedule {schedule_id} updated.", ephemeral=True
            )
        except ScheduleConflictError as exc:
            ids_str = ", ".join(str(i) for i in exc.conflict_ids)
            await interaction.followup.send(
                f"Update would overlap with existing schedule(s) {ids_str}.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("schedules update failed for id %d", schedule_id)
            await interaction.followup.send(f"Error: {exc}.", ephemeral=True)

    @app_commands.command(name="delete", description="Delete a specific schedule by its ID.")
    @app_commands.describe(schedule_id="The schedule ID shown in /qb schedules list.")
    async def delete_schedule(
        self, interaction: discord.Interaction, schedule_id: int
    ) -> None:
        sched = self._svc.schedule_repo.get(schedule_id)
        if sched is None:
            await interaction.response.send_message(
                f"Schedule {schedule_id} not found.", ephemeral=True
            )
            return

        quiz = self._svc.quiz_repo.get(sched.quiz_id)
        quiz_name = quiz.quiz_name if quiz else f"quiz {sched.quiz_id}"

        self._svc.schedule_svc.delete_schedule(schedule_id)

        await interaction.response.send_message(
            f"Deleted schedule {schedule_id} for **{quiz_name}**.", ephemeral=True
        )


def _validate_update_code(
    random: bool, code: str | None, provided_code: bool
) -> str | None:
    if not random and provided_code and not code:
        return "Provide a `code` value when `random=false`."
    if random and provided_code:
        return "Cannot specify both `random=true` and a fixed `code`."
    return None
