from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class LessonStage(str, Enum):
    GREETING = "greeting"
    INTRODUCE_WORD = "introduce_word"
    EXERCISE = "exercise"
    FEEDBACK = "feedback"
    FAREWELL = "farewell"
    COMPLETED = "completed"


class ExerciseType(str, Enum):
    REPEAT = "repeat"
    QUESTION = "question"
    CHOICE = "choice"


class ChildIntent(str, Enum):
    CORRECT_ANSWER = "correct_answer"
    WRONG_ANSWER = "wrong_answer"
    PARTIAL_ANSWER = "partial_answer"
    OFF_TOPIC = "off_topic"
    SILENCE = "silence"
    CHILD_REPLIED = "child_replied"


class FeedbackType(str, Enum):
    POSITIVE = "positive"
    GIVE_ANSWER = "give_answer"


class Message(BaseModel):
    role: str  # "child" or "charlie"
    text: str


class LessonState(BaseModel):
    session_id: str
    words: list[str]
    current_word_index: int = 0
    stage: LessonStage = LessonStage.GREETING
    exercise_type: ExerciseType | None = None
    attempts: int = 0
    feedback_type: FeedbackType | None = None
    conversation_history: list[Message] = Field(default_factory=list)
    child_name: str | None = None
    completed_words: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def current_word(self) -> str | None:
        if 0 <= self.current_word_index < len(self.words):
            return self.words[self.current_word_index]
        return None

    @property
    def has_next_word(self) -> bool:
        return self.current_word_index < len(self.words) - 1

    @property
    def progress(self) -> str:
        done = len(self.completed_words)
        total = len(self.words)
        return f"{done}/{total}"

    @property
    def is_finished(self) -> bool:
        return self.stage == LessonStage.COMPLETED
