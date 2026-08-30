from __future__ import annotations

from canvas_code_bot.canvas.client import CanvasClient
from canvas_code_bot.canvas.engine_rules import detect_engine
from canvas_code_bot.core.models import CanvasQuizInfo, Quiz, QuizEngine


class _NewQuizClient:
    """Operations against /api/quiz/v1/."""

    def __init__(self, client: CanvasClient) -> None:
        self._client = client

    def _path(self, course_id: int, resource_id: int) -> str:
        return f"/api/quiz/v1/courses/{course_id}/quizzes/{resource_id}"

    async def get_quiz_info(
        self, course_id: int, assignment_id: int
    ) -> CanvasQuizInfo:
        data = await self._client.get(self._path(course_id, assignment_id))
        settings = data.get("quiz_settings", {})
        return CanvasQuizInfo(
            assignment_id=assignment_id,
            title=data.get("title", ""),
            requires_access_code=bool(
                settings.get("require_student_access_code", False)
            ),
            engine=QuizEngine.NEW,
            resource_id=assignment_id,
            current_access_code=settings.get("student_access_code") or None,
        )

    async def set_access_code(self, quiz: Quiz, code: str) -> int:
        status, _ = await self._client.patch(
            self._path(quiz.course_id, quiz.resource_id),
            {"quiz": {"quiz_settings": {"student_access_code": code}}},
        )
        return status

    async def verify_access_code(self, quiz: Quiz, code: str) -> bool:
        data = await self._client.get(self._path(quiz.course_id, quiz.resource_id))
        actual = data.get("quiz_settings", {}).get("student_access_code") or None
        return actual == code


class _ClassicQuizClient:
    """Operations against /api/v1/courses/.../quizzes/."""

    def __init__(self, client: CanvasClient) -> None:
        self._client = client

    def _path(self, course_id: int, quiz_id: int) -> str:
        return f"/api/v1/courses/{course_id}/quizzes/{quiz_id}"

    async def get_quiz_info(
        self, course_id: int, quiz_id: int, assignment_id: int
    ) -> CanvasQuizInfo:
        return await self._fetch(course_id, quiz_id, assignment_id)

    async def get_quiz_by_quiz_id(
        self, course_id: int, quiz_id: int
    ) -> CanvasQuizInfo:
        data = await self._client.get(self._path(course_id, quiz_id))
        assignment_id = int(data.get("assignment_id", 0))
        return self._build_info(data, quiz_id, assignment_id)

    async def _fetch(
        self, course_id: int, quiz_id: int, assignment_id: int
    ) -> CanvasQuizInfo:
        data = await self._client.get(self._path(course_id, quiz_id))
        return self._build_info(data, quiz_id, assignment_id)

    def _build_info(
        self, data: dict, quiz_id: int, assignment_id: int
    ) -> CanvasQuizInfo:
        return CanvasQuizInfo(
            assignment_id=assignment_id,
            title=data.get("title", ""),
            requires_access_code=bool(
                data.get("require_student_access_code", False)
            ),
            engine=QuizEngine.CLASSIC,
            resource_id=quiz_id,
            current_access_code=data.get("access_code") or None,
        )

    async def set_access_code(self, quiz: Quiz, code: str) -> int:
        status, _ = await self._client.put(
            self._path(quiz.course_id, quiz.resource_id),
            {"quiz": {"access_code": code}},
        )
        return status

    async def verify_access_code(self, quiz: Quiz, code: str) -> bool:
        data = await self._client.get(self._path(quiz.course_id, quiz.resource_id))
        actual = data.get("access_code") or None
        return actual == code


class CanvasQuizGateway:
    """CanvasPort implementation for Classic and New Quizzes."""

    def __init__(self, client: CanvasClient) -> None:
        self._client = client
        self._new = _NewQuizClient(client)
        self._classic = _ClassicQuizClient(client)

    async def get_quiz(self, course_id: int, assignment_id: int) -> CanvasQuizInfo:
        """Fetch quiz metadata for an assignment, detecting the engine automatically.

        Raises CanvasAuthError, CanvasNotFoundError, CanvasError on API failure.
        Raises ValueError if the assignment is not a quiz.
        """
        assignment_data = await self._client.get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
        )
        engine, resource_id = detect_engine(assignment_data)

        if engine == QuizEngine.NEW:
            return await self._new.get_quiz_info(course_id, assignment_id)
        return await self._classic.get_quiz_info(course_id, resource_id, assignment_id)

    async def get_classic_quiz_by_quiz_id(
        self, course_id: int, quiz_id: int
    ) -> CanvasQuizInfo:
        """Fetch Classic quiz metadata by quiz_id.

        The returned CanvasQuizInfo.assignment_id is populated from the API response.
        """
        return await self._classic.get_quiz_by_quiz_id(course_id, quiz_id)

    async def set_access_code(self, quiz: Quiz, code: str) -> int:
        if quiz.engine == QuizEngine.NEW:
            return await self._new.set_access_code(quiz, code)
        return await self._classic.set_access_code(quiz, code)

    async def verify_access_code(self, quiz: Quiz, code: str) -> bool:
        if quiz.engine == QuizEngine.NEW:
            return await self._new.verify_access_code(quiz, code)
        return await self._classic.verify_access_code(quiz, code)
