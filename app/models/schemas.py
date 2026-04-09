from pydantic import BaseModel, Field

from app.models.exercises import DEFAULT_WORDS


class LessonStartRequest(BaseModel):
    word_list: list[str] = Field(default_factory=lambda: list(DEFAULT_WORDS))
    child_name: str | None = None


class LessonMessageRequest(BaseModel):
    session_id: str
    text: str


class LessonStateResponse(BaseModel):
    stage: str
    current_word: str | None
    progress: str
    is_finished: bool


class LessonStartResponse(BaseModel):
    session_id: str
    charlie_response: str
    lesson_state: LessonStateResponse


class LessonMessageResponse(BaseModel):
    charlie_response: str
    lesson_state: LessonStateResponse
