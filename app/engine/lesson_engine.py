import uuid

from app.engine.state_machine import StateMachine
from app.exceptions import LessonAlreadyCompletedError, SessionNotFoundError
from app.models.exercises import get_exercise
from app.models.state import (
    ChildIntent,
    FeedbackType,
    LessonStage,
    LessonState,
    Message,
)
from app.models.turn import TurnContext
from app.protocols import LLMServiceProtocol, SessionStoreProtocol


class LessonEngine:
    """Orchestrates the lesson: ties together StateMachine, LLMService, and SessionStore.

    Each child message produces exactly ONE LLM call for response generation,
    ensuring Charlie speaks in one coherent message.
    """

    def __init__(
        self,
        llm_service: LLMServiceProtocol,
        session_store: SessionStoreProtocol,
        state_machine: StateMachine | None = None,
    ) -> None:
        self._llm = llm_service
        self._store = session_store
        self._sm = state_machine or StateMachine()

    async def start_lesson(
        self, word_list: list[str], child_name: str | None = None
    ) -> tuple[str, str, LessonState]:
        """Start a new lesson. Returns (session_id, greeting_text, state)."""
        session_id = str(uuid.uuid4())

        state = LessonState(
            session_id=session_id,
            words=word_list,
            child_name=child_name,
        )

        greeting = await self._llm.generate_greeting(state)
        state.conversation_history.append(Message(role="charlie", text=greeting))

        self._store.create(state)
        return session_id, greeting, state

    async def handle_message(
        self, session_id: str, child_text: str
    ) -> tuple[str, LessonState]:
        """Process a child's message. Returns (charlie_response, updated_state)."""
        state = self._store.get(session_id)
        if state is None:
            raise SessionNotFoundError(session_id)
        if state.is_finished:
            raise LessonAlreadyCompletedError(session_id)

        state.conversation_history.append(Message(role="child", text=child_text))

        if state.stage == LessonStage.GREETING:
            turn, state = self._handle_greeting(state)

        elif state.stage == LessonStage.INTRODUCE_WORD:
            turn, state = self._handle_introduce_word(state)

        elif state.stage == LessonStage.EXERCISE:
            intent = await self._llm.evaluate_intent(state, child_text)
            turn, state = self._handle_exercise(state, child_text, intent)

        else:
            turn = TurnContext(child_text=child_text)
            state = self._sm.apply_auto_transitions(state)

        response = await self._llm.generate_turn_response(state, turn)
        state.conversation_history.append(Message(role="charlie", text=response))
        self._store.update(session_id, state)
        return response, state

    # --- Stage handlers ---

    def _handle_greeting(
        self, state: LessonState
    ) -> tuple[TurnContext, LessonState]:
        """Child replied to greeting → introduce first word."""
        state = self._sm.transition(state, ChildIntent.CHILD_REPLIED)
        # Now in INTRODUCE_WORD — Charlie will present the word and wait

        turn = TurnContext(
            is_greeting_reply=True,
            child_name=state.child_name,
            introduce_word=state.current_word,
        )
        return turn, state

    def _handle_introduce_word(
        self, state: LessonState
    ) -> tuple[TurnContext, LessonState]:
        """Child reacted to word introduction → move to exercise."""
        word = state.current_word
        state = self._sm.transition(state, ChildIntent.CHILD_REPLIED)
        exercise = get_exercise(state.current_word) if state.current_word else None

        turn = TurnContext(
            exercise_word=word,
            exercise=exercise,
        )
        return turn, state

    def _handle_exercise(
        self, state: LessonState, child_text: str, intent: ChildIntent
    ) -> tuple[TurnContext, LessonState]:
        """Handle child's answer to an exercise. May stay or cascade."""
        prev_word = state.current_word
        prev_exercise = get_exercise(prev_word) if prev_word else None
        prev_attempts = state.attempts

        state = self._sm.transition(state, intent)

        # --- Staying in EXERCISE (wrong / partial / off-topic / silence) ---
        if state.stage == LessonStage.EXERCISE:
            turn = TurnContext(
                child_text=child_text,
                child_intent=intent,
                retry_word=prev_word,
                retry_exercise=prev_exercise,
                retry_attempt=state.attempts,
            )
            return turn, state

        # --- Left EXERCISE → FEEDBACK → cascade ---
        feedback_type = state.feedback_type
        correct_answer = None
        if feedback_type == FeedbackType.GIVE_ANSWER and prev_exercise:
            correct_answer = prev_exercise.accept_patterns[0]

        # Auto-transitions: FEEDBACK → INTRODUCE_WORD (or FAREWELL → COMPLETED)
        state = self._sm.apply_auto_transitions(state)

        turn = TurnContext(
            child_text=child_text,
            child_intent=intent,
            feedback_type=feedback_type,
            feedback_word=prev_word,
            correct_answer=correct_answer,
            retry_attempt=prev_attempts + 1,
        )

        if state.stage == LessonStage.INTRODUCE_WORD:
            # Feedback + introduce next word (child will respond before exercise)
            turn.introduce_word = state.current_word
        elif state.stage in (LessonStage.FAREWELL, LessonStage.COMPLETED):
            turn.is_farewell = True
            turn.completed_words = list(state.completed_words)

        return turn, state
