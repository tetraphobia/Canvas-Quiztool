"""
Unit tests for canvas/engine_rules.py.

Pure data-in / data-out — no I/O.
"""
import pytest

from canvas_code_bot.canvas.engine_rules import detect_engine
from canvas_code_bot.core.models import QuizEngine


# ── New Quizzes detection ──────────────────────────────────────────────────────

def test_new_quiz_detected_by_lti_flag():
    data = {"id": 456, "is_quiz_lti_assignment": True, "submission_types": ["external_tool"]}
    engine, resource_id = detect_engine(data)
    assert engine == QuizEngine.NEW


def test_new_quiz_resource_id_is_assignment_id():
    data = {"id": 789, "is_quiz_lti_assignment": True}
    _, resource_id = detect_engine(data)
    assert resource_id == 789


def test_new_quiz_id_as_string_is_coerced():
    """Canvas sometimes returns numeric ids as strings."""
    data = {"id": "456", "is_quiz_lti_assignment": True}
    _, resource_id = detect_engine(data)
    assert resource_id == 456


def test_new_quiz_lti_flag_false_falls_through():
    """is_quiz_lti_assignment=False should not match New Quizzes."""
    data = {"id": 456, "is_quiz_lti_assignment": False, "quiz_id": 789}
    engine, resource_id = detect_engine(data)
    assert engine == QuizEngine.CLASSIC
    assert resource_id == 789


# ── Classic detection ──────────────────────────────────────────────────────────

def test_classic_detected_by_quiz_id():
    data = {"id": 456, "quiz_id": 123, "submission_types": ["online_quiz"]}
    engine, resource_id = detect_engine(data)
    assert engine == QuizEngine.CLASSIC


def test_classic_resource_id_is_quiz_id():
    data = {"id": 456, "quiz_id": 321}
    _, resource_id = detect_engine(data)
    assert resource_id == 321


def test_classic_quiz_id_as_string_is_coerced():
    data = {"id": 456, "quiz_id": "321"}
    _, resource_id = detect_engine(data)
    assert resource_id == 321


# ── Unknown / error cases ──────────────────────────────────────────────────────

def test_raises_when_no_engine_detected():
    with pytest.raises(ValueError, match="Cannot determine quiz engine"):
        detect_engine({"id": 456, "submission_types": ["online_upload"]})


def test_raises_on_empty_dict():
    with pytest.raises(ValueError):
        detect_engine({})


def test_raises_includes_key_list():
    with pytest.raises(ValueError, match="submission_types"):
        detect_engine({"id": 1, "submission_types": ["discussion"]})
