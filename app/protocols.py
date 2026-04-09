"""Port interfaces (protocols) for dependency inversion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.models.state import LessonState
    from app.models.turn import TurnContext

from app.models.state import ChildIntent  # noqa: E402


class LLMResult:
    """Value object returned by LLM service."""

    __slots__ = ("response_text", "child_intent")

    def __init__(self, response_text: str, child_intent: ChildIntent | None = None):
        self.response_text = response_text
        self.child_intent = child_intent


class LLMServiceProtocol(Protocol):
    async def generate_greeting(self, state: LessonState) -> str:
        """Generate Charlie's greeting. Returns response text."""
        ...

    async def evaluate_intent(self, state: LessonState, child_text: str) -> ChildIntent:
        """Classify the child's answer. Returns intent only, no response text."""
        ...

    async def generate_turn_response(self, state: LessonState, turn: TurnContext) -> str:
        """Generate Charlie's complete response for a turn. One call, one coherent reply."""
        ...


class SessionStoreProtocol(Protocol):
    def create(self, state: LessonState) -> str: ...
    def get(self, session_id: str) -> LessonState | None: ...
    def update(self, session_id: str, state: LessonState) -> None: ...
    def delete(self, session_id: str) -> None: ...
