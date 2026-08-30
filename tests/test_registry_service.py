"""
Tests for core/services.py — RegistryService and ConfigService.

All Canvas and repo interactions are provided by fakes.
"""
from datetime import datetime

import pytest

from canvas_code_bot.core.exceptions import CanvasNotFoundError
from canvas_code_bot.core.models import CanvasQuizInfo, Config, Quiz, QuizEngine
from canvas_code_bot.core.services import ConfigService, RegistryService

_NOW = datetime(2026, 8, 27, 12, 0, 0)
_INFO = CanvasQuizInfo(
    assignment_id=100, title="Midterm", requires_access_code=True,
    engine=QuizEngine.NEW, resource_id=100,
)
_CLASSIC_INFO = CanvasQuizInfo(
    assignment_id=200, title="Classic Quiz", requires_access_code=True,
    engine=QuizEngine.CLASSIC, resource_id=50,
)


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeCanvas:
    def __init__(self, quiz_info=None, classic_info=None, raises=None):
        self._info = quiz_info or _INFO
        self._classic_info = classic_info or _CLASSIC_INFO
        self._raises = raises
        self.get_calls: list[tuple] = []
        self.get_classic_calls: list[tuple] = []

    async def get_quiz(self, course_id, assignment_id):
        self.get_calls.append((course_id, assignment_id))
        if self._raises:
            raise self._raises
        return self._info

    async def get_classic_quiz_by_quiz_id(self, course_id, quiz_id):
        self.get_classic_calls.append((course_id, quiz_id))
        if self._raises:
            raise self._raises
        return self._classic_info

    async def set_access_code(self, quiz, code): ...
    async def verify_access_code(self, quiz, code): return True


class FakeQuizRepo:
    def __init__(self, quizzes=None):
        quizzes = quizzes or []
        self._quizzes: dict[int, Quiz] = {q.id: q for q in quizzes}
        self._by_assignment = {(q.course_id, q.assignment_id): q for q in quizzes}
        self._next_id = max((q.id for q in quizzes), default=0) + 1
        self.removed: list[int] = []
        self.channel_updates: list[tuple] = []

    def add(self, quiz: Quiz) -> Quiz:
        quiz.id = self._next_id
        self._next_id += 1
        self._quizzes[quiz.id] = quiz
        self._by_assignment[(quiz.course_id, quiz.assignment_id)] = quiz
        return quiz

    def get(self, quiz_id):
        return self._quizzes.get(quiz_id)

    def get_by_assignment(self, course_id, assignment_id):
        return self._by_assignment.get((course_id, assignment_id))

    def get_by_resource_id(self, course_id, resource_id):
        for q in self._quizzes.values():
            if q.course_id == course_id and q.resource_id == resource_id:
                return q
        return None

    def list_all(self):
        return list(self._quizzes.values())

    def update_current_code(self, quiz_id, code, at): ...

    def update_notify_channel(self, quiz_id, channel_id):
        self.channel_updates.append((quiz_id, channel_id))

    def remove(self, quiz_id):
        quiz = self._quizzes.pop(quiz_id, None)
        if quiz:
            self._by_assignment.pop((quiz.course_id, quiz.assignment_id), None)
        self.removed.append(quiz_id)


class FakeConfigRepo:
    def __init__(self, channel_id=None):
        self._cfg = Config(updated_by=0, updated_at=_NOW, notify_channel_id=channel_id)
        self.set_calls: list[tuple] = []

    def get(self):
        return self._cfg

    def set_channel(self, channel_id, updated_by, at):
        self._cfg.notify_channel_id = channel_id
        self.set_calls.append((channel_id, updated_by))


# ── RegistryService tests ──────────────────────────────────────────────────────

async def test_add_quiz_calls_canvas():
    canvas = FakeCanvas()
    svc = RegistryService(quiz_repo=FakeQuizRepo(), canvas=canvas)
    await svc.add_quiz(course_id=10, assignment_id=100, added_by=999)
    assert canvas.get_calls == [(10, 100)]


async def test_add_quiz_uses_canvas_title():
    info = CanvasQuizInfo(
        assignment_id=100, title="Final Exam", requires_access_code=True,
        engine=QuizEngine.NEW, resource_id=100,
    )
    svc = RegistryService(quiz_repo=FakeQuizRepo(), canvas=FakeCanvas(quiz_info=info))
    quiz = await svc.add_quiz(course_id=10, assignment_id=100, added_by=999)
    assert quiz.quiz_name == "Final Exam"


async def test_add_quiz_assigns_id():
    repo = FakeQuizRepo()
    svc = RegistryService(quiz_repo=repo, canvas=FakeCanvas())
    quiz = await svc.add_quiz(course_id=10, assignment_id=100, added_by=999)
    assert quiz.id != 0
    assert len(repo.list_all()) == 1


async def test_add_quiz_sets_course_name_from_id():
    svc = RegistryService(quiz_repo=FakeQuizRepo(), canvas=FakeCanvas())
    quiz = await svc.add_quiz(course_id=42, assignment_id=100, added_by=999)
    assert quiz.course_name == "Course 42"


async def test_add_quiz_already_registered_raises():
    existing = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="Course 10",
        quiz_name="Midterm", added_by=999, added_at=_NOW,
    )
    repo = FakeQuizRepo(quizzes=[existing])
    svc = RegistryService(quiz_repo=repo, canvas=FakeCanvas())
    with pytest.raises(ValueError, match="already registered"):
        await svc.add_quiz(course_id=10, assignment_id=100, added_by=999)


async def test_add_quiz_propagates_canvas_error():
    canvas = FakeCanvas(raises=CanvasNotFoundError("not found", http_status=404))
    svc = RegistryService(quiz_repo=FakeQuizRepo(), canvas=canvas)
    with pytest.raises(CanvasNotFoundError):
        await svc.add_quiz(course_id=10, assignment_id=999, added_by=999)


async def test_add_quiz_by_quiz_id_calls_canvas():
    canvas = FakeCanvas()
    svc = RegistryService(quiz_repo=FakeQuizRepo(), canvas=canvas)
    await svc.add_quiz_by_quiz_id(course_id=10, quiz_id=50, added_by=999)
    assert canvas.get_classic_calls == [(10, 50)]


async def test_add_quiz_by_quiz_id_uses_canvas_title():
    svc = RegistryService(quiz_repo=FakeQuizRepo(), canvas=FakeCanvas())
    quiz = await svc.add_quiz_by_quiz_id(course_id=10, quiz_id=50, added_by=999)
    assert quiz.quiz_name == "Classic Quiz"


async def test_add_quiz_by_quiz_id_assigns_id():
    repo = FakeQuizRepo()
    svc = RegistryService(quiz_repo=repo, canvas=FakeCanvas())
    quiz = await svc.add_quiz_by_quiz_id(course_id=10, quiz_id=50, added_by=999)
    assert quiz.id != 0
    assert len(repo.list_all()) == 1


async def test_add_quiz_by_quiz_id_stores_classic_engine():
    svc = RegistryService(quiz_repo=FakeQuizRepo(), canvas=FakeCanvas())
    quiz = await svc.add_quiz_by_quiz_id(course_id=10, quiz_id=50, added_by=999)
    assert quiz.engine == QuizEngine.CLASSIC
    assert quiz.resource_id == 50


async def test_add_quiz_by_quiz_id_already_registered_raises():
    existing = Quiz(
        id=1, course_id=10, assignment_id=200, course_name="Course 10",
        quiz_name="Classic Quiz", added_by=999, added_at=_NOW,
        engine=QuizEngine.CLASSIC, resource_id=50,
    )
    repo = FakeQuizRepo(quizzes=[existing])
    svc = RegistryService(quiz_repo=repo, canvas=FakeCanvas())
    with pytest.raises(ValueError, match="already registered"):
        await svc.add_quiz_by_quiz_id(course_id=10, quiz_id=50, added_by=999)


async def test_add_quiz_by_quiz_id_propagates_canvas_error():
    canvas = FakeCanvas(raises=CanvasNotFoundError("not found", http_status=404))
    svc = RegistryService(quiz_repo=FakeQuizRepo(), canvas=canvas)
    with pytest.raises(CanvasNotFoundError):
        await svc.add_quiz_by_quiz_id(course_id=10, quiz_id=999, added_by=999)


def test_remove_quiz_delegates_to_repo():
    existing = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="Course 10",
        quiz_name="Midterm", added_by=999, added_at=_NOW,
    )
    repo = FakeQuizRepo(quizzes=[existing])
    svc = RegistryService(quiz_repo=repo, canvas=FakeCanvas())
    svc.remove_quiz(quiz_id=1)
    assert 1 in repo.removed


# ── ConfigService tests ────────────────────────────────────────────────────────

def test_set_global_channel_persists():
    config_repo = FakeConfigRepo()
    svc = ConfigService(quiz_repo=FakeQuizRepo(), config_repo=config_repo)
    svc.set_global_channel(channel_id=555, updated_by=1)
    assert len(config_repo.set_calls) == 1
    assert config_repo.set_calls[0][0] == 555


def test_set_quiz_channel_updates_repo():
    existing = Quiz(
        id=1, course_id=10, assignment_id=100, course_name="Course 10",
        quiz_name="Midterm", added_by=999, added_at=_NOW,
    )
    repo = FakeQuizRepo(quizzes=[existing])
    svc = ConfigService(quiz_repo=repo, config_repo=FakeConfigRepo())
    svc.set_quiz_channel(quiz_id=1, channel_id=777, updated_by=1)
    assert (1, 777) in repo.channel_updates


def test_get_returns_config():
    config_repo = FakeConfigRepo(channel_id=42)
    svc = ConfigService(quiz_repo=FakeQuizRepo(), config_repo=config_repo)
    cfg = svc.get()
    assert cfg.notify_channel_id == 42
