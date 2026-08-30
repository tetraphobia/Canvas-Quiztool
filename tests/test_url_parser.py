"""Unit tests for canvas/url_parser.py."""
import pytest
from canvas_code_bot.canvas.url_parser import ParsedUrl, parse_quiz_url


# ── /assignments/ URL (New Quizzes or Classic via assignments view) ────────────

def test_standard_instructure_url():
    p = parse_quiz_url("https://school.instructure.com/courses/123/assignments/456")
    assert p.course_id == 123
    assert p.assignment_id == 456
    assert p.quiz_id is None


def test_beta_subdomain():
    p = parse_quiz_url("https://school.beta.instructure.com/courses/100/assignments/200")
    assert p.course_id == 100
    assert p.assignment_id == 200


def test_custom_canvas_domain():
    p = parse_quiz_url("https://canvas.myschool.edu/courses/9/assignments/11")
    assert p.course_id == 9
    assert p.assignment_id == 11


def test_http_scheme():
    p = parse_quiz_url("http://school.instructure.com/courses/1/assignments/2")
    assert p.course_id == 1
    assert p.assignment_id == 2


def test_trailing_slash():
    p = parse_quiz_url("https://school.instructure.com/courses/1/assignments/2/")
    assert p.assignment_id == 2


def test_edit_suffix():
    p = parse_quiz_url("https://school.instructure.com/courses/77/assignments/88/edit")
    assert p.course_id == 77
    assert p.assignment_id == 88


def test_query_string():
    p = parse_quiz_url("https://school.instructure.com/courses/10/assignments/20?return_to=/")
    assert p.assignment_id == 20


def test_fragment():
    p = parse_quiz_url("https://school.instructure.com/courses/10/assignments/20#overview")
    assert p.assignment_id == 20


def test_strips_surrounding_whitespace():
    p = parse_quiz_url("  https://school.instructure.com/courses/5/assignments/6  ")
    assert p.course_id == 5
    assert p.assignment_id == 6


def test_large_ids():
    p = parse_quiz_url("https://school.instructure.com/courses/9999999/assignments/8888888")
    assert p.course_id == 9_999_999
    assert p.assignment_id == 8_888_888


# ── /quizzes/ URL (Classic native URL) ────────────────────────────────────────

def test_classic_quizzes_url():
    p = parse_quiz_url("https://school.instructure.com/courses/123/quizzes/456")
    assert p.course_id == 123
    assert p.quiz_id == 456
    assert p.assignment_id is None


def test_classic_quizzes_url_beta():
    p = parse_quiz_url("https://school.beta.instructure.com/courses/10/quizzes/99")
    assert p.course_id == 10
    assert p.quiz_id == 99


def test_classic_quizzes_url_with_trailing_slash():
    p = parse_quiz_url("https://school.instructure.com/courses/1/quizzes/2/")
    assert p.quiz_id == 2


def test_classic_quizzes_url_with_edit_suffix():
    p = parse_quiz_url("https://school.instructure.com/courses/7/quizzes/8/edit")
    assert p.course_id == 7
    assert p.quiz_id == 8


# ── ParsedUrl properties ──────────────────────────────────────────────────────

def test_parsed_url_is_assignment():
    p = ParsedUrl(course_id=1, assignment_id=2)
    assert p.assignment_id is not None
    assert p.quiz_id is None


def test_parsed_url_is_quiz():
    p = ParsedUrl(course_id=1, quiz_id=3)
    assert p.quiz_id is not None
    assert p.assignment_id is None


# ── Error cases ───────────────────────────────────────────────────────────────

def test_no_matching_segment_raises():
    with pytest.raises(ValueError):
        parse_quiz_url("https://school.instructure.com/courses/123/pages/some-page")


def test_no_courses_segment_raises():
    with pytest.raises(ValueError):
        parse_quiz_url("https://school.instructure.com/quizzes/456")


def test_empty_string_raises():
    with pytest.raises(ValueError):
        parse_quiz_url("")


def test_whitespace_only_raises():
    with pytest.raises(ValueError):
        parse_quiz_url("   ")


def test_no_scheme_raises():
    with pytest.raises(ValueError):
        parse_quiz_url("school.instructure.com/courses/1/assignments/2")


def test_just_domain_raises():
    with pytest.raises(ValueError):
        parse_quiz_url("https://school.instructure.com")


def test_random_string_raises():
    with pytest.raises(ValueError):
        parse_quiz_url("not a url at all")
