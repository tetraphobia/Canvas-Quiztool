"""
Tests for CanvasQuizGateway and its two engine strategies.

Uses a FakeClient so no real HTTP calls are made.
"""
import pytest

from canvas_code_bot.canvas.quizzes import CanvasQuizGateway
from canvas_code_bot.core.exceptions import CanvasAuthError, CanvasNotFoundError
from canvas_code_bot.core.models import Quiz, QuizEngine
from datetime import datetime

_NOW = datetime(2026, 8, 27, 12, 0, 0)

# ── Fake client ───────────────────────────────────────────────────────────────

class FakeClient:
    """Duck-typed stand-in for CanvasClient."""

    def __init__(
        self,
        get_responses: dict | None = None,
        patch_result: tuple[int, dict | None] = (200, {}),
        put_result: tuple[int, dict | None] = (200, {}),
        get_exc: Exception | None = None,
        patch_exc: Exception | None = None,
    ) -> None:
        self._get_responses = get_responses or {}
        self._patch_result = patch_result
        self._put_result = put_result
        self._get_exc = get_exc
        self._patch_exc = patch_exc
        self.get_calls: list[str] = []
        self.patch_calls: list[tuple[str, dict]] = []
        self.put_calls: list[tuple[str, dict]] = []

    async def get(self, path: str) -> dict:
        self.get_calls.append(path)
        if self._get_exc:
            raise self._get_exc
        return self._get_responses.get(path, {})

    async def patch(self, path: str, payload: dict) -> tuple[int, dict | None]:
        self.patch_calls.append((path, payload))
        if self._patch_exc:
            raise self._patch_exc
        return self._patch_result

    async def put(self, path: str, payload: dict) -> tuple[int, dict | None]:
        self.put_calls.append((path, payload))
        return self._put_result


# ── Canned API responses ───────────────────────────────────────────────────────

_NEW_ASSIGNMENT = {
    "id": 456,
    "is_quiz_lti_assignment": True,
    "submission_types": ["external_tool"],
}

_CLASSIC_ASSIGNMENT = {
    "id": 456,
    "quiz_id": 789,
    "submission_types": ["online_quiz"],
}

_NEW_QUIZ_RESPONSE = {
    "id": "456",
    "title": "Midterm Exam",
    "quiz_settings": {
        "require_student_access_code": True,
        "student_access_code": "ABC123",
    },
}

_CLASSIC_QUIZ_RESPONSE = {
    "id": 789,
    "title": "Classic Midterm",
    "require_student_access_code": True,
    "access_code": "XYZ789",
}

_CLASSIC_QUIZ_BY_QUIZ_ID_RESPONSE = {
    "id": 789,
    "assignment_id": 456,
    "title": "Classic Midterm",
    "require_student_access_code": True,
    "access_code": "XYZ789",
}


def _new_client(extra_get=None, **kw):
    responses = {
        "/api/v1/courses/10/assignments/456": _NEW_ASSIGNMENT,
        "/api/quiz/v1/courses/10/quizzes/456": _NEW_QUIZ_RESPONSE,
    }
    if extra_get:
        responses.update(extra_get)
    return FakeClient(get_responses=responses, **kw)


def _classic_client(extra_get=None, **kw):
    responses = {
        "/api/v1/courses/10/assignments/456": _CLASSIC_ASSIGNMENT,
        "/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_RESPONSE,
    }
    if extra_get:
        responses.update(extra_get)
    return FakeClient(get_responses=responses, **kw)


def _new_quiz(**kw) -> Quiz:
    return Quiz(
        id=1, course_id=10, assignment_id=456,
        course_name="CS101", quiz_name="Midterm",
        added_by=99, added_at=_NOW,
        engine=QuizEngine.NEW, resource_id=456,
        **kw,
    )


def _classic_quiz(**kw) -> Quiz:
    return Quiz(
        id=1, course_id=10, assignment_id=456,
        course_name="CS101", quiz_name="Classic Midterm",
        added_by=99, added_at=_NOW,
        engine=QuizEngine.CLASSIC, resource_id=789,
        **kw,
    )


# ── get_quiz — New Quizzes engine ──────────────────────────────────────────────

async def test_get_quiz_new_probes_assignment_then_quiz_api():
    client = _new_client()
    gw = CanvasQuizGateway(client)
    await gw.get_quiz(10, 456)
    assert "/api/v1/courses/10/assignments/456" in client.get_calls
    assert "/api/quiz/v1/courses/10/quizzes/456" in client.get_calls


async def test_get_quiz_new_engine_detected():
    gw = CanvasQuizGateway(_new_client())
    info = await gw.get_quiz(10, 456)
    assert info.engine == QuizEngine.NEW


async def test_get_quiz_new_resource_id_is_assignment_id():
    gw = CanvasQuizGateway(_new_client())
    info = await gw.get_quiz(10, 456)
    assert info.resource_id == 456


async def test_get_quiz_new_maps_title():
    gw = CanvasQuizGateway(_new_client())
    info = await gw.get_quiz(10, 456)
    assert info.title == "Midterm Exam"


async def test_get_quiz_new_maps_access_code():
    gw = CanvasQuizGateway(_new_client())
    info = await gw.get_quiz(10, 456)
    assert info.current_access_code == "ABC123"


async def test_get_quiz_new_empty_code_becomes_none():
    responses = {
        "/api/v1/courses/10/assignments/456": _NEW_ASSIGNMENT,
        "/api/quiz/v1/courses/10/quizzes/456": {
            "id": "456", "title": "X",
            "quiz_settings": {"student_access_code": ""},
        },
    }
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    info = await gw.get_quiz(10, 456)
    assert info.current_access_code is None


# ── get_quiz — Classic engine ──────────────────────────────────────────────────

async def test_get_quiz_classic_engine_detected():
    gw = CanvasQuizGateway(_classic_client())
    info = await gw.get_quiz(10, 456)
    assert info.engine == QuizEngine.CLASSIC


async def test_get_quiz_classic_resource_id_is_quiz_id():
    gw = CanvasQuizGateway(_classic_client())
    info = await gw.get_quiz(10, 456)
    assert info.resource_id == 789


async def test_get_quiz_classic_maps_title():
    gw = CanvasQuizGateway(_classic_client())
    info = await gw.get_quiz(10, 456)
    assert info.title == "Classic Midterm"


async def test_get_quiz_classic_maps_access_code():
    gw = CanvasQuizGateway(_classic_client())
    info = await gw.get_quiz(10, 456)
    assert info.current_access_code == "XYZ789"


async def test_get_quiz_classic_probes_classic_quizzes_api():
    client = _classic_client()
    gw = CanvasQuizGateway(client)
    await gw.get_quiz(10, 456)
    assert "/api/v1/courses/10/quizzes/789" in client.get_calls


# ── get_quiz error propagation ─────────────────────────────────────────────────

async def test_get_quiz_propagates_auth_error():
    exc = CanvasAuthError("401", http_status=401)
    gw = CanvasQuizGateway(FakeClient(get_exc=exc))
    with pytest.raises(CanvasAuthError):
        await gw.get_quiz(10, 456)


async def test_get_quiz_propagates_not_found():
    exc = CanvasNotFoundError("404", http_status=404)
    gw = CanvasQuizGateway(FakeClient(get_exc=exc))
    with pytest.raises(CanvasNotFoundError):
        await gw.get_quiz(10, 456)


# ── set_access_code — New Quizzes ──────────────────────────────────────────────

async def test_set_new_sends_patch_with_correct_payload():
    client = FakeClient(patch_result=(200, {}))
    gw = CanvasQuizGateway(client)
    await gw.set_access_code(_new_quiz(), "NEWCODE")
    assert client.patch_calls[0][1] == {
        "quiz": {"quiz_settings": {"student_access_code": "NEWCODE"}}
    }


async def test_set_new_uses_correct_path():
    client = FakeClient(patch_result=(200, {}))
    gw = CanvasQuizGateway(client)
    await gw.set_access_code(_new_quiz(), "X")
    assert client.patch_calls[0][0] == "/api/quiz/v1/courses/10/quizzes/456"


async def test_set_new_returns_200():
    gw = CanvasQuizGateway(FakeClient(patch_result=(200, {})))
    assert await gw.set_access_code(_new_quiz(), "CODE") == 200


async def test_set_new_accepts_204():
    gw = CanvasQuizGateway(FakeClient(patch_result=(204, None)))
    assert await gw.set_access_code(_new_quiz(), "CODE") == 204


async def test_set_new_propagates_auth_error():
    exc = CanvasAuthError("401", http_status=401)
    gw = CanvasQuizGateway(FakeClient(patch_exc=exc))
    with pytest.raises(CanvasAuthError):
        await gw.set_access_code(_new_quiz(), "X")


# ── set_access_code — Classic ──────────────────────────────────────────────────

async def test_set_classic_sends_put_with_correct_payload():
    client = FakeClient(put_result=(200, {}))
    gw = CanvasQuizGateway(client)
    await gw.set_access_code(_classic_quiz(), "CLASSIC_CODE")
    assert client.put_calls[0][1] == {"quiz": {"access_code": "CLASSIC_CODE"}}


async def test_set_classic_uses_correct_path():
    client = FakeClient(put_result=(200, {}))
    gw = CanvasQuizGateway(client)
    await gw.set_access_code(_classic_quiz(), "X")
    assert client.put_calls[0][0] == "/api/v1/courses/10/quizzes/789"


async def test_set_classic_returns_200():
    gw = CanvasQuizGateway(FakeClient(put_result=(200, {})))
    assert await gw.set_access_code(_classic_quiz(), "CODE") == 200


# ── verify_access_code — New Quizzes ──────────────────────────────────────────

async def test_verify_new_true_when_code_matches():
    responses = {"/api/quiz/v1/courses/10/quizzes/456": _NEW_QUIZ_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    assert await gw.verify_access_code(_new_quiz(), "ABC123") is True


async def test_verify_new_false_when_code_differs():
    responses = {"/api/quiz/v1/courses/10/quizzes/456": _NEW_QUIZ_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    assert await gw.verify_access_code(_new_quiz(), "WRONG") is False


# ── verify_access_code — Classic ──────────────────────────────────────────────

async def test_verify_classic_true_when_code_matches():
    responses = {"/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    assert await gw.verify_access_code(_classic_quiz(), "XYZ789") is True


async def test_verify_classic_false_when_code_differs():
    responses = {"/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    assert await gw.verify_access_code(_classic_quiz(), "WRONG") is False


# ── get_classic_quiz_by_quiz_id ────────────────────────────────────────────────

async def test_get_classic_by_quiz_id_calls_correct_path():
    responses = {"/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_BY_QUIZ_ID_RESPONSE}
    client = FakeClient(get_responses=responses)
    gw = CanvasQuizGateway(client)
    await gw.get_classic_quiz_by_quiz_id(10, 789)
    assert "/api/v1/courses/10/quizzes/789" in client.get_calls


async def test_get_classic_by_quiz_id_engine_is_classic():
    responses = {"/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_BY_QUIZ_ID_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    info = await gw.get_classic_quiz_by_quiz_id(10, 789)
    assert info.engine == QuizEngine.CLASSIC


async def test_get_classic_by_quiz_id_resource_id_is_quiz_id():
    responses = {"/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_BY_QUIZ_ID_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    info = await gw.get_classic_quiz_by_quiz_id(10, 789)
    assert info.resource_id == 789


async def test_get_classic_by_quiz_id_reads_assignment_id_from_response():
    responses = {"/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_BY_QUIZ_ID_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    info = await gw.get_classic_quiz_by_quiz_id(10, 789)
    assert info.assignment_id == 456


async def test_get_classic_by_quiz_id_maps_title():
    responses = {"/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_BY_QUIZ_ID_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    info = await gw.get_classic_quiz_by_quiz_id(10, 789)
    assert info.title == "Classic Midterm"


async def test_get_classic_by_quiz_id_maps_access_code():
    responses = {"/api/v1/courses/10/quizzes/789": _CLASSIC_QUIZ_BY_QUIZ_ID_RESPONSE}
    gw = CanvasQuizGateway(FakeClient(get_responses=responses))
    info = await gw.get_classic_quiz_by_quiz_id(10, 789)
    assert info.current_access_code == "XYZ789"
