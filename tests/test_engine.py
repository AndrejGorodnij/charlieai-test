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
    """After greeting, Charlie introduces the first word (no exercise yet)."""
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("Great! Let's learn about CAT! A cat is a fluffy animal.")
    response, state = await eng.handle_message(session_id, "hello!")

    assert state.stage == LessonStage.INTRODUCE_WORD
    assert state.current_word == "cat"

    turn = mock_llm.last_turn
    assert turn.is_greeting_reply
    assert turn.introduce_word == "cat"
    assert turn.exercise_word is None  # no exercise yet!


@pytest.mark.asyncio
async def test_introduce_word_then_exercise(engine):
    """After intro, child reacts → Charlie asks the exercise question."""
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    # Greeting → INTRODUCE_WORD
    mock_llm.set_turn_response("Let's learn CAT!")
    await eng.handle_message(session_id, "hello!")

    # INTRODUCE_WORD → EXERCISE
    mock_llm.set_turn_response("What sound does a cat make?")
    response, state = await eng.handle_message(session_id, "ok!")

    assert state.stage == LessonStage.EXERCISE
    assert state.current_word == "cat"

    turn = mock_llm.last_turn
    assert turn.exercise_word == "cat"
    assert turn.exercise is not None


@pytest.mark.asyncio
async def test_correct_answer_introduces_next_word(engine):
    """Correct answer → feedback + introduce next word (no exercise in same turn)."""
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat", "dog"])

    # Greeting → INTRODUCE_WORD
    mock_llm.set_turn_response("Let's learn CAT!")
    await eng.handle_message(session_id, "hi")

    # INTRODUCE_WORD → EXERCISE
    mock_llm.set_turn_response("What sound?")
    await eng.handle_message(session_id, "ok")

    # Correct answer → FEEDBACK → INTRODUCE_WORD (dog)
    mock_llm.set_intent(ChildIntent.CORRECT_ANSWER)
    mock_llm.set_turn_response("Yay! Now let's learn about DOG! A dog is a friendly animal.")
    response, state = await eng.handle_message(session_id, "meow")

    assert state.stage == LessonStage.INTRODUCE_WORD
    assert state.current_word == "dog"
    assert "cat" in state.completed_words

    turn = mock_llm.last_turn
    assert turn.feedback_word == "cat"
    assert turn.introduce_word == "dog"
    assert turn.exercise_word is None  # exercise comes next turn


@pytest.mark.asyncio
async def test_correct_answer_last_word_farewell(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("CAT intro")
    await eng.handle_message(session_id, "hi")

    mock_llm.set_turn_response("What sound?")
    await eng.handle_message(session_id, "ok")

    mock_llm.set_intent(ChildIntent.CORRECT_ANSWER)
    mock_llm.set_turn_response("Amazing! You learned cat! Bye bye!")
    response, state = await eng.handle_message(session_id, "meow")

    assert state.is_finished
    turn = mock_llm.last_turn
    assert turn.is_farewell
    assert "cat" in turn.completed_words


@pytest.mark.asyncio
async def test_wrong_answer_stays_in_exercise(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("CAT intro")
    await eng.handle_message(session_id, "hi")
    mock_llm.set_turn_response("What sound?")
    await eng.handle_message(session_id, "ok")

    mock_llm.set_intent(ChildIntent.WRONG_ANSWER)
    mock_llm.set_turn_response("Not quite! A cat says... Try again!")
    response, state = await eng.handle_message(session_id, "bark")

    assert state.stage == LessonStage.EXERCISE
    assert state.attempts == 1

    turn = mock_llm.last_turn
    assert turn.retry_word == "cat"
    assert turn.child_intent == ChildIntent.WRONG_ANSWER


@pytest.mark.asyncio
async def test_silence_stays_in_exercise(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("CAT intro")
    await eng.handle_message(session_id, "hi")
    mock_llm.set_turn_response("What sound?")
    await eng.handle_message(session_id, "ok")

    mock_llm.set_intent(ChildIntent.SILENCE)
    mock_llm.set_turn_response("It's okay! What sound does a cat make?")
    response, state = await eng.handle_message(session_id, "")

    assert state.stage == LessonStage.EXERCISE
    turn = mock_llm.last_turn
    assert turn.child_intent == ChildIntent.SILENCE


@pytest.mark.asyncio
async def test_off_topic_stays_in_exercise(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("CAT intro")
    await eng.handle_message(session_id, "hi")
    mock_llm.set_turn_response("What sound?")
    await eng.handle_message(session_id, "ok")

    mock_llm.set_intent(ChildIntent.OFF_TOPIC)
    mock_llm.set_turn_response("Ice cream is yummy! But what sound does a cat make?")
    response, state = await eng.handle_message(session_id, "I like ice cream")

    assert state.stage == LessonStage.EXERCISE
    turn = mock_llm.last_turn
    assert turn.child_intent == ChildIntent.OFF_TOPIC


@pytest.mark.asyncio
async def test_max_attempts_gives_answer(engine):
    eng, mock_llm, _ = engine
    session_id, _, _ = await eng.start_lesson(word_list=["cat"])

    mock_llm.set_turn_response("CAT intro")
    await eng.handle_message(session_id, "hi")
    mock_llm.set_turn_response("What sound?")
    await eng.handle_message(session_id, "ok")

    mock_llm.set_intent(ChildIntent.WRONG_ANSWER)
    for _ in range(2):
        mock_llm.set_turn_response("Try again!")
        await eng.handle_message(session_id, "wrong")

    mock_llm.set_turn_response("A cat says meow! Great try! Bye bye!")
    response, state = await eng.handle_message(session_id, "wrong")

    assert state.is_finished
    turn = mock_llm.last_turn
    assert turn.feedback_word == "cat"
    assert turn.correct_answer == "meow"
    assert turn.is_farewell


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
