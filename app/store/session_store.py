from app.models.state import LessonState


class SessionStore:
    """In-memory session storage."""

    def __init__(self) -> None:
        self._sessions: dict[str, LessonState] = {}

    def create(self, state: LessonState) -> str:
        self._sessions[state.session_id] = state
        return state.session_id

    def get(self, session_id: str) -> LessonState | None:
        return self._sessions.get(session_id)

    def update(self, session_id: str, state: LessonState) -> None:
        self._sessions[session_id] = state

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
