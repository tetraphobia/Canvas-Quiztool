from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# /courses/<int>/assignments/<int>
_ASSIGNMENT_RE = re.compile(r"/courses/(\d+)/assignments/(\d+)")
# /courses/<int>/quizzes/<int>  — Classic quiz native URL
_CLASSIC_QUIZ_RE = re.compile(r"/courses/(\d+)/quizzes/(\d+)")


@dataclass
class ParsedUrl:
    """
    Result of parsing a Canvas quiz URL.

    Exactly one of ``assignment_id`` or ``quiz_id`` is set:
    - assignment_id: from ``/courses/<cid>/assignments/<aid>``  (New or Classic)
    - quiz_id:       from ``/courses/<cid>/quizzes/<qid>``      (Classic only)
    """
    course_id: int
    assignment_id: int | None = None
    quiz_id: int | None = None


def parse_quiz_url(url: str) -> ParsedUrl:
    """
    Parse a Canvas quiz URL into a ``ParsedUrl``.

    Accepts:
    - ``/courses/<cid>/assignments/<aid>`` — New Quizzes or Classic (via assignments view)
    - ``/courses/<cid>/quizzes/<qid>``    — Classic Quizzes (native URL)

    Raises:
        ValueError: if the URL is not a valid absolute URL or matches neither pattern.
    """
    url = url.strip()

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Could not parse URL: {url!r}") from exc

    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            f"Not a valid absolute URL (missing scheme or host): {url!r}"
        )

    m = _ASSIGNMENT_RE.search(parsed.path)
    if m:
        return ParsedUrl(
            course_id=int(m.group(1)),
            assignment_id=int(m.group(2)),
        )

    m = _CLASSIC_QUIZ_RE.search(parsed.path)
    if m:
        return ParsedUrl(
            course_id=int(m.group(1)),
            quiz_id=int(m.group(2)),
        )

    raise ValueError(
        f"URL does not contain /courses/<id>/assignments/<id> "
        f"or /courses/<id>/quizzes/<id>: {url!r}"
    )
