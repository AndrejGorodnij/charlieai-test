"""Integration tests for FastAPI endpoints with dependency injection overrides."""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_engine, get_session_store, reset
from app.engine.lesson_engine import LessonEngine
from app.main import app
from app.models.state import ChildIntent
from app.models.turn import TurnContext
from app.store.session_store import SessionStore


class MockLLMService:
    """Satisfies LLMServiceProtocol structurally."""

    def __init__(self):
        self._greeting = "Hi! I'm Charlie the fox!"
        self._turn_response = "Let's learn some words!"
        self._intent = ChildIntent.WRONG_ANSWER

    async def generate_greeting(self, state) -> str:
        return self._greeting

    async def evaluate_intent(self, state, child_text: str) -> ChildIntent:
        return self._intent

    async def generate_turn_response(self, state, turn: TurnContext) -> str:
        return self._turn_response


@pytest.fixture(autouse=True)
def _override_dependencies():
    """Override DI providers for all API tests."""
    reset()

    mock_llm = MockLLMService()
    store = SessionStore()
    engine = LessonEngine(llm_service=mock_llm, session_store=store)

    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_session_store] = lambda: store

    yield mock_llm

    app.dependency_overrides.clear()
    reset()


@pytest.fixture
def client():
    return TestClient(app)


def test_start_lesson(client):
    response = client.post("/lesson/start", json={"word_list": ["cat", "dog"]})
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "charlie_response" in data
    assert data["lesson_state"]["stage"] == "greeting"
    assert data["lesson_state"]["progress"] == "0/2"


def test_start_lesson_default_words(client):
    response = client.post("/lesson/start", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["lesson_state"]["progress"] == "0/3"


def test_start_lesson_empty_word_list(client):
    response = client.post("/lesson/start", json={"word_list": []})
    assert response.status_code == 422


def test_get_status(client):
    start_resp = client.post("/lesson/start", json={"word_list": ["cat"]})
    session_id = start_resp.json()["session_id"]

    response = client.get(f"/lesson/{session_id}/status")
    assert response.status_code == 200
    assert response.json()["stage"] == "greeting"


def test_get_status_not_found(client):
    response = client.get("/lesson/nonexistent/status")
    assert response.status_code == 404


def test_send_message_not_found(client):
    response = client.post(
        "/lesson/message",
        json={"session_id": "nonexistent", "text": "hello"},
    )
    assert response.status_code == 404


def test_send_message_after_greeting(client):
    start_resp = client.post("/lesson/start", json={"word_list": ["cat"]})
    session_id = start_resp.json()["session_id"]

    response = client.post(
        "/lesson/message",
        json={"session_id": session_id, "text": "yes!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "charlie_response" in data
    assert data["lesson_state"]["stage"] == "introduce_word"
