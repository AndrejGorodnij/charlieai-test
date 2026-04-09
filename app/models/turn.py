"""Turn context — describes what happened in a single conversational turn."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.exercises import ExerciseDefinition
from app.models.state import ChildIntent, FeedbackType


@dataclass
class TurnContext:
    """Everything the LLM needs to generate one coherent response for a turn.

    Built by the engine AFTER all state transitions are decided.
    The LLM sees this as a single prompt → produces a single reply.
    """

    # --- What the child said ---
    child_text: str = ""
    child_intent: ChildIntent | None = None

    # --- Greeting (first turn only) ---
    is_greeting_reply: bool = False
    child_name: str | None = None

    # --- Feedback on previous exercise ---
    feedback_type: FeedbackType | None = None
    feedback_word: str | None = None
    correct_answer: str | None = None  # used when feedback_type == GIVE_ANSWER

    # --- New word introduction ---
    introduce_word: str | None = None

    # --- Repeat word (pronunciation practice) ---
    repeat_word: str | None = None

    # --- New exercise to ask ---
    exercise_word: str | None = None
    exercise: ExerciseDefinition | None = None

    # --- Review (end-of-lesson recap) ---
    is_review: bool = False
    review_words: list[str] = field(default_factory=list)

    # --- Farewell ---
    is_farewell: bool = False
    completed_words: list[str] = field(default_factory=list)

    # --- Staying in exercise (wrong answer / silence / off-topic) ---
    retry_word: str | None = None
    retry_exercise: ExerciseDefinition | None = None
    retry_attempt: int = 0
