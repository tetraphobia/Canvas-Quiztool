from __future__ import annotations

import secrets

from canvas_code_bot.core.models import CodePolicy


class RandomCodeGenerator:
    """Generates access codes from a CodePolicy."""

    def generate(self, policy: CodePolicy) -> str:
        if policy.length < 1:
            raise ValueError(
                f"Code length must be at least 1, got {policy.length}"
            )
        if not policy.charset:
            raise ValueError("Charset must not be empty")

        return "".join(secrets.choice(policy.charset) for _ in range(policy.length))
