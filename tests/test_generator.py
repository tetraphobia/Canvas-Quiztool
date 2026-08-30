import pytest
from canvas_code_bot.codes.generator import RandomCodeGenerator
from canvas_code_bot.core.models import (
    CodePolicy,
    DEFAULT_CODE_CHARSET,
    DEFAULT_CODE_LENGTH,
)

@pytest.fixture
def gen() -> RandomCodeGenerator:
    return RandomCodeGenerator()

def test_default_length(gen):
    code = gen.generate(CodePolicy())
    assert len(code) == DEFAULT_CODE_LENGTH

def test_default_charset_chars_only(gen):
    valid = set(DEFAULT_CODE_CHARSET)
    for _ in range(50):
        code = gen.generate(CodePolicy())
        assert all(c in valid for c in code), f"Unexpected char in {code!r}"

def test_excluded_ambiguous_chars_absent(gen):
    excluded = set("IO01")
    for _ in range(200):
        code = gen.generate(CodePolicy())
        assert not any(c in excluded for c in code), (
            f"Ambiguous char found in {code!r}"
        )

def test_custom_length(gen):
    code = gen.generate(CodePolicy(length=10))
    assert len(code) == 10


def test_length_one(gen):
    code = gen.generate(CodePolicy(length=1))
    assert len(code) == 1


def test_custom_charset(gen):
    code = gen.generate(CodePolicy(charset="ABC", length=30))
    assert all(c in "ABC" for c in code)
    assert len(code) == 30


def test_single_char_charset(gen):
    code = gen.generate(CodePolicy(charset="X", length=5))
    assert code == "XXXXX"


def test_outputs_are_not_all_identical(gen):
    codes = {gen.generate(CodePolicy()) for _ in range(20)}
    assert len(codes) > 1

def test_zero_length_raises(gen):
    with pytest.raises(ValueError, match="length"):
        gen.generate(CodePolicy(length=0))


def test_negative_length_raises(gen):
    with pytest.raises(ValueError, match="length"):
        gen.generate(CodePolicy(length=-3))


def test_empty_charset_raises(gen):
    with pytest.raises(ValueError, match="[Cc]harset"):
        gen.generate(CodePolicy(charset=""))
