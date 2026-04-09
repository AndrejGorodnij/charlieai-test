"""Tests for LessonEngine with mock LLM (protocol-based)."""

import pytest
import pytest_asyncio

from app.engine.lesson_engine import LessonEngine
from app.exceptions import LessonAlreadyCompletedError, SessionNotFoundError
from app.models.state import ChildIntent, LessonStage
from app.models.turn import TurnContext
from app.store.session_store import SessionStore


class MockLLMService:
    """Satisfies LLMServiceProtocol structurally — no inheritance needed."""

    def __init__(self):
        self._greeting = "Hi! I'm Charlie the fox!"
        self._turn_response = "Default response"
        self._intent = ChildIntent.WRONG_ANSWER
        self.last_turn: TurnContext | None = None

    def set_greeting(self, text: str):
        self._greeting = text

    def set_turn_response(self, text: str):
        self._turn_response = text

    def set_intent(self, intent: ChildIntent):
        self._intent = intent

    async def generate_greeting(self, state) -> str:
        return self._greeting

    async def evaluate_intent(self, state, child_text: str) -> ChildIntent:
        return self._intent

    async def generate_turn_response(self, state, turn: TurnContext) -> str:
        self.last_turn = turn
        return self._turn_response


@pytest_asyncio.fixture
async def engine():
    mock_llm = MockLLMService()
    store = SessionStore()
    eng = LessonEngine(llm_service=mock_llm, session_store=store)
    return eng, mock_llm, store


# --- Helpers ---

async def advance_to_exercise(eng, mock_llm, session_id):
    """Helper: advance from GREETING through INTRODUCE → REPEAT → EXERCISE."""
    mock_llm.set_turn_response("Let's learn CAT!")
    await eng.handle_message(session_id, "hello!")  # greeting → introduce

    mock_llm.set_turn_response("Can you say CAT?")
    await eng.handle_message(session_id, "ok!")  # introduce → repeat

    mock_llm.set_turn_response("What sound does a cat make?")
    await eng.handle_message(session_id, "cat")  # repeat → exercise


# --- Tests ---

@pytest.mark.asyncio
async def test_start_lesson(engine):
    eng, mock_llm, _ = engine
    mock_llm.set_greeting("Hi! I'm Charlie!")

    session_id, greeting, state = await eng.start_lesson(
        word_list=["cat", "dog"], child_name="Марія"
    )

    assert session_id
    assert greeting == "Hi! I'm Charlie!"
    assert state.stage == LessonStage.GREETING
    assert state.child_name == "Марія"


@pytest.mark.asyncio
async def test_greeting_introduces_word(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("Meet CAT — a fluffy animal!")
    response, state = await eng.handle_message(session_id, "hello!")

    assert state.stage == LessonStage.INTRODUCE_WORD
    turn = mock_llm.last_turn
    assert turn.is_greeting_reply
    assert turn.introduce_word == "cat"


@pytest.mark.asyncio
async def test_introduce_moves_to_repeat(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("Meet CAT!")
    await eng.handle_message(session_id, "hello!")

    mock_llm.set_turn_response("Can you say CAT?")
    response, state = await eng.handle_message(session_id, "cool!")

    assert state.stage == LessonStage.REPEAT_WORD
    turn = mock_llm.last_turn
    assert turn.repeat_word == "cat"


@pytest.mark.asyncio
async def test_repeat_moves_to_exercise(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("Meet CAT!")
    await eng.handle_message(session_id, "hello!")

    mock_llm.set_turn_response("Can you say CAT?")
    await eng.handle_message(session_id, "cool!")

    mock_llm.set_turn_response("What sound does a cat make?")
    response, state = await eng.handle_message(session_id, "cat!")

    assert state.stage == LessonStage.EXERCISE
    turn = mock_llm.last_turn
    assert turn.exercise_word == "cat"
    assert turn.exercise is not None


@pytest.mark.asyncio
async def test_correct_answer_introduces_next_word(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat", "dog"])
    await advance_to_exercise(eng, mock_llm, session_id)

    mock_llm.set_intent(ChildIntent.CORRECT_ANSWER)
    mock_llm.set_turn_response("Yay! Now meet DOG!")
    response, state = await eng.handle_message(session_id, "meow")

    assert state.stage == LessonStage.INTRODUCE_WORD
    assert state.current_word == "dog"
    assert "cat" in state.completed_words

    turn = mock_llm.last_turn
    assert turn.feedback_word == "cat"
    assert turn.introduce_word == "dog"


@pytest.mark.asyncio
async def test_correct_answer_last_word_goes_to_review(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])
    await advance_to_exercise(eng, mock_llm, session_id)

    mock_llm.set_intent(ChildIntent.CORRECT_ANSWER)
    mock_llm.set_turn_response("Yay! Let's review!")
    response, state = await eng.handle_message(session_id, "meow")

    assert state.stage == LessonStage.REVIEW

    turn = mock_llm.last_turn
    assert turn.is_review
    assert "cat" in turn.review_words


@pytest.mark.asyncio
async def test_review_then_farewell(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])
    await advance_to_exercise(eng, mock_llm, session_id)

    mock_llm.set_intent(ChildIntent.CORRECT_ANSWER)
    mock_llm.set_turn_response("Let's review!")
    await eng.handle_message(session_id, "meow")

    mock_llm.set_turn_response("Bye bye! You were amazing!")
    response, state = await eng.handle_message(session_id, "cat!")

    assert state.is_finished

    turn = mock_llm.last_turn
    assert turn.is_farewell
    assert "cat" in turn.completed_words


@pytest.mark.asyncio
async def test_wrong_answer_stays_in_exercise(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])
    await advance_to_exercise(eng, mock_llm, session_id)

    mock_llm.set_intent(ChildIntent.WRONG_ANSWER)
    mock_llm.set_turn_response("Hmm, not quite!")
    response, state = await eng.handle_message(session_id, "bark")

    assert state.stage == LessonStage.EXERCISE
    assert state.attempts == 1
    turn = mock_llm.last_turn
    assert turn.retry_word == "cat"


@pytest.mark.asyncio
async def test_silence_stays_in_exercise(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])
    await advance_to_exercise(eng, mock_llm, session_id)

    mock_llm.set_intent(ChildIntent.SILENCE)
    mock_llm.set_turn_response("Don't worry, try again!")
    response, state = await eng.handle_message(session_id, "")

    assert state.stage == LessonStage.EXERCISE
    assert mock_llm.last_turn.child_intent == ChildIntent.SILENCE


@pytest.mark.asyncio
async def test_off_topic_stays_in_exercise(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])
    await advance_to_exercise(eng, mock_llm, session_id)

    mock_llm.set_intent(ChildIntent.OFF_TOPIC)
    mock_llm.set_turn_response("Pizza is yummy! But what sound?")
    response, state = await eng.handle_message(session_id, "I like pizza")

    assert state.stage == LessonStage.EXERCISE
    assert mock_llm.last_turn.child_intent == ChildIntent.OFF_TOPIC


@pytest.mark.asyncio
async def test_max_attempts_gives_answer_then_review(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])
    await advance_to_exercise(eng, mock_llm, session_id)

    mock_llm.set_intent(ChildIntent.WRONG_ANSWER)
    for _ in range(2):
        mock_llm.set_turn_response("Try again!")
        await eng.handle_message(session_id, "wrong")

    mock_llm.set_turn_response("It's meow! Let's review!")
    response, state = await eng.handle_message(session_id, "wrong")

    assert state.stage == LessonStage.REVIEW
    turn = mock_llm.last_turn
    assert turn.correct_answer == "meow"
    assert turn.is_review


@pytest.mark.asyncio
async def test_session_not_found(engine):
    eng, _, _ = engine
    with pytest.raises(SessionNotFoundError):
        await eng.handle_message("nonexistent", "hello")


@pytest.mark.asyncio
async def test_lesson_already_completed(engine):
    eng, mock_llm, store = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    state = store.get(session_id)
    state.stage = LessonStage.COMPLETED
    store.update(session_id, state)

    with pytest.raises(LessonAlreadyCompletedError):
        await eng.handle_message(session_id, "hello")
