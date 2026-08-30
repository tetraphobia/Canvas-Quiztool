"""
Tests for core/services.py — RotationService.

All Canvas, notifier, and repo interactions are provided by fakes.
backoff_base=0.0 keeps tests instant (asyncio.sleep(0) just yields).
"""
from datetime import datetime

import pytest

from canvas_code_bot.core.exceptions import CanvasAuthError, CanvasNotFoundError
from canvas_code_bot.core.models import (
    CodePolicy,
    Config,
    Quiz,
    RotationOutcome,
    TriggeredBy,
)
from canvas_code_bot.core.services import RotationService

# ── Fakes ─────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 8, 27, 12, 0, 0)
_ADMIN_ID = 42


class FakeCodeGen:
    def __init__(self, code: str = "GENCODE") -> None:
        self._code = code

    def generate(self, policy: CodePolicy) -> str:
        return self._code


class FakeCanvas:
    """
    Configurable fake CanvasPort.

    patch_responses: list of results per attempt.
        Each item is either an int (HTTP status) or an Exception to raise.
    verify_returns: list of booleans (True=code matches), one per verify call.
    """

    def __init__(self, patch_responses=None, verify_returns=None):
        self._patches = list(patch_responses or [200])
        self._verifies = list(verify_returns or [True])
        self.patch_calls: list[tuple] = []
        self.verify_calls: list[tuple] = []

    async def set_access_code(self, quiz, code):
        result = self._patches.pop(0) if self._patches else 200
        self.patch_calls.append((quiz.course_id, quiz.assignment_id, code))
        if isinstance(result, Exception):
            raise result
        return result

    async def verify_access_code(self, quiz, code):
        result = self._verifies.pop(0) if self._verifies else True
        self.verify_calls.append((quiz.course_id, quiz.assignment_id, code))
        if isinstance(result, Exception):
            raise result
        return result

    async def get_quiz(self, course_id, assignment_id):
        raise NotImplementedError


class FakeQuizRepo:
    def __init__(self):
        self.updated: list[tuple] = []

    def update_current_code(self, quiz_id, code, at):
        self.updated.append((quiz_id, code))

    def add(self, quiz): ...
    def get(self, quiz_id): ...
    def get_by_assignment(self, course_id, assignment_id): ...
    def list_all(self): return []
    def remove(self, quiz_id): ...


class FakeHistoryRepo:
    def __init__(self):
        self.recorded = []

    def record(self, entry):
        self.recorded.append(entry)
        return entry

    def last_for_quiz(self, quiz_id): return None


class FakeNotifier:
    def __init__(self):
        self.success_calls: list[tuple] = []
        self.group_success_calls: list[tuple] = []
        self.error_calls: list[tuple] = []

    async def notify_success(self, channel_id, quiz, code):
        self.success_calls.append((channel_id, quiz.id, code))

    async def notify_group_success(self, channel_id, quizzes, code):
        self.group_success_calls.append((channel_id, [q.id for q in quizzes], code))

    async def notify_error(self, channel_id, quiz, error, admin_id):
        self.error_calls.append((channel_id, quiz.id, admin_id))


class FakeConfigRepo:
    def __init__(self, channel_id=None):
        self._cfg = Config(updated_by=0, updated_at=_NOW, notify_channel_id=channel_id)

    def get(self):
        return self._cfg

    def set_channel(self, channel_id, updated_by, at): ...


# ── Helpers ───────────────────────────────────────────────────────────────────

def _quiz(channel_id=None) -> Quiz:
    return Quiz(
        id=1,
        course_id=10,
        assignment_id=100,
        course_name="CS101",
        quiz_name="Midterm",
        added_by=999,
        added_at=_NOW,
        notify_channel_id=channel_id,
    )


def _service(canvas=None, notifier=None, config_channel=None, max_attempts=3):
    return RotationService(
        code_gen=FakeCodeGen(),
        canvas=canvas or FakeCanvas(),
        quiz_repo=FakeQuizRepo(),
        history_repo=FakeHistoryRepo(),
        notifier=notifier or FakeNotifier(),
        config_repo=FakeConfigRepo(channel_id=config_channel),
        admin_discord_id=_ADMIN_ID,
        max_attempts=max_attempts,
        backoff_base=0.0,   # no real sleep
    )


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_success_on_first_attempt():
    notifier = FakeNotifier()
    svc = _service(notifier=notifier, config_channel=777)
    result = await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert result.outcome == RotationOutcome.SUCCESS
    assert result.attempts == 1


async def test_generated_code_used_when_no_fixed_code():
    canvas = FakeCanvas()
    svc = _service(canvas=canvas, config_channel=1)
    await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert canvas.patch_calls[0][2] == "GENCODE"


async def test_fixed_code_overrides_generator():
    canvas = FakeCanvas()
    svc = _service(canvas=canvas, config_channel=1)
    await svc.rotate(_quiz(), TriggeredBy.MANUAL, fixed_code="FIXED1")
    assert canvas.patch_calls[0][2] == "FIXED1"


async def test_success_updates_quiz_repo():
    quiz_repo = FakeQuizRepo()
    svc = RotationService(
        code_gen=FakeCodeGen(),
        canvas=FakeCanvas(),
        quiz_repo=quiz_repo,
        history_repo=FakeHistoryRepo(),
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(channel_id=1),
        admin_discord_id=_ADMIN_ID,
        max_attempts=3,
        backoff_base=0.0,
    )
    await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert len(quiz_repo.updated) == 1
    assert quiz_repo.updated[0][0] == 1   # quiz_id
    assert quiz_repo.updated[0][1] == "GENCODE"


async def test_success_records_history():
    history = FakeHistoryRepo()
    svc = RotationService(
        code_gen=FakeCodeGen(),
        canvas=FakeCanvas(),
        quiz_repo=FakeQuizRepo(),
        history_repo=history,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(channel_id=1),
        admin_discord_id=_ADMIN_ID,
        max_attempts=3,
        backoff_base=0.0,
    )
    await svc.rotate(_quiz(), TriggeredBy.SCHEDULE, schedule_id=5)
    assert len(history.recorded) == 1
    entry = history.recorded[0]
    assert entry.outcome == RotationOutcome.SUCCESS
    assert entry.schedule_id == 5
    assert entry.triggered_by == TriggeredBy.SCHEDULE


async def test_success_notifies_channel():
    notifier = FakeNotifier()
    svc = _service(notifier=notifier, config_channel=888)
    await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert len(notifier.success_calls) == 1
    assert notifier.success_calls[0][0] == 888


async def test_quiz_channel_overrides_global():
    notifier = FakeNotifier()
    svc = _service(notifier=notifier, config_channel=111)
    quiz = _quiz(channel_id=999)  # per-quiz channel
    await svc.rotate(quiz, TriggeredBy.MANUAL)
    assert notifier.success_calls[0][0] == 999   # quiz channel wins


# ── Retry ─────────────────────────────────────────────────────────────────────

async def test_retries_on_transient_error():
    from canvas_code_bot.core.exceptions import CanvasError
    canvas = FakeCanvas(
        patch_responses=[CanvasError("timeout", http_status=503), 200],
        verify_returns=[True],
    )
    svc = _service(canvas=canvas, config_channel=1)
    result = await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert result.outcome == RotationOutcome.SUCCESS
    assert result.attempts == 2


async def test_retries_on_verify_failure():
    canvas = FakeCanvas(
        patch_responses=[200, 200],
        verify_returns=[False, True],   # first verify fails, second succeeds
    )
    svc = _service(canvas=canvas, config_channel=1)
    result = await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert result.outcome == RotationOutcome.SUCCESS
    assert result.attempts == 2


async def test_exhausted_retries_record_failed():
    from canvas_code_bot.core.exceptions import CanvasError
    canvas = FakeCanvas(
        patch_responses=[
            CanvasError("err", http_status=500),
            CanvasError("err", http_status=500),
            CanvasError("err", http_status=500),
        ],
    )
    history = FakeHistoryRepo()
    svc = RotationService(
        code_gen=FakeCodeGen(),
        canvas=canvas,
        quiz_repo=FakeQuizRepo(),
        history_repo=history,
        notifier=FakeNotifier(),
        config_repo=FakeConfigRepo(channel_id=1),
        admin_discord_id=_ADMIN_ID,
        max_attempts=3,
        backoff_base=0.0,
    )
    result = await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert result.outcome == RotationOutcome.FAILED
    assert result.attempts == 3
    assert history.recorded[0].outcome == RotationOutcome.FAILED


async def test_no_retry_on_auth_error():
    canvas = FakeCanvas(
        patch_responses=[CanvasAuthError("401", http_status=401)],
    )
    svc = _service(canvas=canvas, config_channel=1, max_attempts=3)
    result = await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert result.outcome == RotationOutcome.FAILED
    assert result.attempts == 1          # stopped immediately
    assert len(canvas.patch_calls) == 1  # only one attempt


async def test_no_retry_on_not_found():
    canvas = FakeCanvas(
        patch_responses=[CanvasNotFoundError("404", http_status=404)],
    )
    svc = _service(canvas=canvas, config_channel=1, max_attempts=3)
    result = await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert result.outcome == RotationOutcome.FAILED
    assert result.attempts == 1


# ── Notification on failure ───────────────────────────────────────────────────

async def test_failure_calls_notify_error():
    from canvas_code_bot.core.exceptions import CanvasError
    canvas = FakeCanvas(patch_responses=[CanvasError("boom", http_status=500)] * 3)
    notifier = FakeNotifier()
    svc = _service(canvas=canvas, notifier=notifier, config_channel=555, max_attempts=3)
    await svc.rotate(_quiz(), TriggeredBy.MANUAL)
    assert len(notifier.error_calls) == 1
    assert notifier.error_calls[0][0] == 555
    assert notifier.error_calls[0][2] == _ADMIN_ID


async def test_no_notify_when_no_channel_configured():
    from canvas_code_bot.core.exceptions import CanvasError
    canvas = FakeCanvas(patch_responses=[CanvasError("boom")] * 3)
    notifier = FakeNotifier()
    svc = _service(canvas=canvas, notifier=notifier, config_channel=None, max_attempts=3)
    await svc.rotate(_quiz(channel_id=None), TriggeredBy.MANUAL)
    assert len(notifier.error_calls) == 0  # silently skipped


# ── rotate_group ──────────────────────────────────────────────────────────────

async def test_rotate_group_uses_same_code_for_all_quizzes():
    """All quizzes in the group must receive exactly the same generated code."""
    canvas = FakeCanvas(
        patch_responses=[200, 200],
        verify_returns=[True, True],
    )
    svc = _service(canvas=canvas, config_channel=1)
    quiz1 = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="CS", quiz_name="Q1",
        added_by=1, added_at=_NOW,
    )
    quiz2 = Quiz(
        id=2, course_id=10, assignment_id=200, course_name="CS", quiz_name="Q2",
        added_by=1, added_at=_NOW,
    )
    await svc.rotate_group([(quiz1, 1), (quiz2, 2)], TriggeredBy.SCHEDULE)
    # Both quizzes must have been patched with the same code
    code1 = canvas.patch_calls[0][2]
    code2 = canvas.patch_calls[1][2]
    assert code1 == code2


async def test_rotate_group_fires_for_each_quiz():
    canvas = FakeCanvas(
        patch_responses=[200, 200],
        verify_returns=[True, True],
    )
    svc = _service(canvas=canvas, config_channel=1)
    quiz1 = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="CS", quiz_name="Q1",
        added_by=1, added_at=_NOW,
    )
    quiz2 = Quiz(
        id=2, course_id=10, assignment_id=200, course_name="CS", quiz_name="Q2",
        added_by=1, added_at=_NOW,
    )
    await svc.rotate_group([(quiz1, None), (quiz2, None)], TriggeredBy.SCHEDULE)
    assert len(canvas.patch_calls) == 2


async def test_rotate_group_uses_fixed_code():
    canvas = FakeCanvas(
        patch_responses=[200, 200],
        verify_returns=[True, True],
    )
    svc = _service(canvas=canvas, config_channel=1)
    quiz1 = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="CS", quiz_name="Q1",
        added_by=1, added_at=_NOW,
    )
    quiz2 = Quiz(
        id=2, course_id=10, assignment_id=200, course_name="CS", quiz_name="Q2",
        added_by=1, added_at=_NOW,
    )
    await svc.rotate_group(
        [(quiz1, None), (quiz2, None)], TriggeredBy.SCHEDULE, fixed_code="SHARED"
    )
    assert canvas.patch_calls[0][2] == "SHARED"
    assert canvas.patch_calls[1][2] == "SHARED"


async def test_rotate_group_empty_pairs_is_noop():
    canvas = FakeCanvas()
    svc = _service(canvas=canvas, config_channel=1)
    await svc.rotate_group([], TriggeredBy.SCHEDULE)
    assert len(canvas.patch_calls) == 0


async def test_rotate_group_sends_one_group_notification_per_channel():
    """rotate_group must send exactly one notify_group_success per channel, not one per quiz."""
    canvas = FakeCanvas(patch_responses=[200, 200], verify_returns=[True, True])
    notifier = FakeNotifier()
    svc = _service(canvas=canvas, notifier=notifier, config_channel=7)
    quiz1 = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="CS", quiz_name="Q1",
        added_by=1, added_at=_NOW,
    )
    quiz2 = Quiz(
        id=2, course_id=10, assignment_id=200, course_name="CS", quiz_name="Q2",
        added_by=1, added_at=_NOW,
    )
    await svc.rotate_group([(quiz1, None), (quiz2, None)], TriggeredBy.SCHEDULE)
    # One combined notification, not two individual ones
    assert len(notifier.group_success_calls) == 1
    assert len(notifier.success_calls) == 0
    ch, quiz_ids, code = notifier.group_success_calls[0]
    assert ch == 7
    assert set(quiz_ids) == {1, 2}


async def test_rotate_group_notify_groups_by_channel():
    """Quizzes on different channels each get their own group notification."""
    canvas = FakeCanvas(patch_responses=[200, 200], verify_returns=[True, True])
    notifier = FakeNotifier()
    svc = _service(canvas=canvas, notifier=notifier, config_channel=99)
    quiz_ch1 = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="CS", quiz_name="Q1",
        notify_channel_id=1, added_by=1, added_at=_NOW,
    )
    quiz_ch2 = Quiz(
        id=2, course_id=10, assignment_id=200, course_name="CS", quiz_name="Q2",
        notify_channel_id=2, added_by=1, added_at=_NOW,
    )
    await svc.rotate_group([(quiz_ch1, None), (quiz_ch2, None)], TriggeredBy.SCHEDULE)
    assert len(notifier.group_success_calls) == 2
    channels_notified = {call[0] for call in notifier.group_success_calls}
    assert channels_notified == {1, 2}


async def test_rotate_group_returns_per_quiz_results():
    """rotate_group must return results in the same order as pairs."""
    canvas = FakeCanvas(patch_responses=[200, 200], verify_returns=[True, True])
    svc = _service(canvas=canvas, config_channel=1)
    quiz1 = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="CS", quiz_name="Q1",
        added_by=1, added_at=_NOW,
    )
    quiz2 = Quiz(
        id=2, course_id=10, assignment_id=200, course_name="CS", quiz_name="Q2",
        added_by=1, added_at=_NOW,
    )
    results = await svc.rotate_group([(quiz1, None), (quiz2, None)], TriggeredBy.SCHEDULE)
    assert len(results) == 2
    assert results[0][0].id == 1
    assert results[1][0].id == 2
    assert all(r.outcome == RotationOutcome.SUCCESS for _, r in results)


async def test_rotate_group_partial_failure_notifies_individually():
    """A failed quiz in a group gets notify_error; the successful ones get a combined embed."""
    canvas = FakeCanvas(
        patch_responses=[200, CanvasNotFoundError(404, "not found")],
        verify_returns=[True],
    )
    notifier = FakeNotifier()
    svc = _service(canvas=canvas, notifier=notifier, config_channel=5)
    quiz_ok = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="CS", quiz_name="Q1",
        added_by=1, added_at=_NOW,
    )
    quiz_fail = Quiz(
        id=2, course_id=10, assignment_id=200, course_name="CS", quiz_name="Q2",
        added_by=1, added_at=_NOW,
    )
    await svc.rotate_group([(quiz_ok, None), (quiz_fail, None)], TriggeredBy.SCHEDULE)
    assert len(notifier.group_success_calls) == 1
    assert notifier.group_success_calls[0][1] == [1]
    assert len(notifier.error_calls) == 1
    assert notifier.error_calls[0][1] == 2
