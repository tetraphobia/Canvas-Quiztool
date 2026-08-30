from __future__ import annotations

from canvas_code_bot.core.models import QuizEngine


def detect_engine(assignment_data: dict) -> tuple[QuizEngine, int]:
    """Returns (engine, resource_id) from a Canvas assignment API response.

    Raises ValueError if the assignment is neither a New Quiz nor a Classic Quiz.
    """
    if assignment_data.get("is_quiz_lti_assignment"):
        return QuizEngine.NEW, int(assignment_data["id"])

    quiz_id = assignment_data.get("quiz_id")
    if quiz_id:
        return QuizEngine.CLASSIC, int(quiz_id)

    raise ValueError(
        "Cannot determine quiz engine from assignment data. "
        "Expected 'is_quiz_lti_assignment' (New Quizzes) or 'quiz_id' (Classic). "
        f"Got keys: {sorted(assignment_data.keys())}"
    )
