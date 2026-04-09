"""FastAPI dependency injection providers."""

from app.engine.lesson_engine import LessonEngine
from app.llm.service import LLMService
from app.protocols import LLMServiceProtocol, SessionStoreProtocol
from app.store.session_store import SessionStore

# Singletons — created once, reused across requests
_session_store: SessionStoreProtocol | None = None
_llm_service: LLMServiceProtocol | None = None
_engine: LessonEngine | None = None


def get_session_store() -> SessionStoreProtocol:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def get_llm_service() -> LLMServiceProtocol:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def get_engine() -> LessonEngine:
    global _engine
    if _engine is None:
        _engine = LessonEngine(
            llm_service=get_llm_service(),
            session_store=get_session_store(),
        )
    return _engine


def reset() -> None:
    """Reset all singletons. Used in tests."""
    global _session_store, _llm_service, _engine
    _session_store = None
    _llm_service = None
    _engine = None
