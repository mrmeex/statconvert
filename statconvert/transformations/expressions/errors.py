from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpressionIssue:
    """One deterministic, JSON-safe expression diagnostic."""

    code: str
    message: str
    start: int
    end: int
    suggestion: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation with stable field ordering."""

        result: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "start": self.start,
            "end": self.end,
        }
        if self.suggestion is not None:
            result["suggestion"] = self.suggestion
        return result


class ExpressionParseError(ValueError):
    """Internal tokenizer/parser failure carrying one safe diagnostic."""

    def __init__(self, issue: ExpressionIssue) -> None:
        super().__init__(issue.message)
        self.issue = issue
