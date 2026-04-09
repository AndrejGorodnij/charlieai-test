from app.models.exercises import get_exercise
from app.models.state import (
    ChildIntent,
    FeedbackType,
    LessonStage,
    LessonState,
)

MAX_ATTEMPTS = 3


class StateMachine:
    """Pure deterministic state machine. No I/O, no side effects.

    Lesson flow:
        GREETING → INTRODUCE_WORD → REPEAT_WORD → EXERCISE → FEEDBACK
                                                                 │
                                                      ┌─────────┤
                                                 has_next    last_word
                                                      │         │
                                                INTRODUCE    REVIEW → FAREWELL → COMPLETED
                                                (next word)

    Child-input stages (wait for message): GREETING, INTRODUCE_WORD, REPEAT_WORD, EXERCISE, REVIEW
    Auto-transition stages (advance immediately): FEEDBACK, FAREWELL
    """

    def transition(self, state: LessonState, intent: ChildIntent) -> LessonState:
        """Apply a child intent event to the current state and return the updated state."""
        handler = self._handlers.get(state.stage)
        if handler is None:
            return state
        return handler(self, state, intent)

    def apply_auto_transitions(self, state: LessonState) -> LessonState:
        """Apply automatic transitions (states that don't wait for child input)."""
        while state.stage in self._auto_stages:
            handler = self._auto_stages[state.stage]
            new_state = handler(self, state)
            if new_state.stage == state.stage:
                break  # safety: prevent infinite loop
            state = new_state
        return state

    # --- Handlers for child-input stages ---

    def _handle_greeting(self, state: LessonState, intent: ChildIntent) -> LessonState:
        return state.model_copy(
            update={
                "stage": LessonStage.INTRODUCE_WORD,
                "current_word_index": 0,
            }
        )

    def _handle_introduce_word(
        self, state: LessonState, intent: ChildIntent
    ) -> LessonState:
        """Child reacted to word introduction → ask them to repeat the word."""
        return state.model_copy(update={"stage": LessonStage.REPEAT_WORD})

    def _handle_repeat_word(
        self, state: LessonState, intent: ChildIntent
    ) -> LessonState:
        """Child tried to repeat the word → move to exercise.

        REPEAT_WORD is intentionally lenient — we always advance to EXERCISE
        regardless of correctness. In a real product with STT, this is where
        pronunciation scoring would happen. For now, Charlie encourages and moves on.
        """
        word = state.current_word
        if word is None:
            return state.model_copy(update={"stage": LessonStage.FAREWELL})

        exercise = get_exercise(word)
        return state.model_copy(
            update={
                "stage": LessonStage.EXERCISE,
                "exercise_type": exercise.exercise_type,
                "attempts": 0,
            }
        )

    def _handle_exercise(self, state: LessonState, intent: ChildIntent) -> LessonState:
        if intent == ChildIntent.CORRECT_ANSWER:
            return state.model_copy(
                update={
                    "stage": LessonStage.FEEDBACK,
                    "feedback_type": FeedbackType.POSITIVE,
                }
            )

        # All non-correct intents: wrong, partial, off_topic, silence
        new_attempts = state.attempts + 1
        if new_attempts >= MAX_ATTEMPTS:
            return state.model_copy(
                update={
                    "stage": LessonStage.FEEDBACK,
                    "feedback_type": FeedbackType.GIVE_ANSWER,
                    "attempts": new_attempts,
                }
            )

        return state.model_copy(update={"attempts": new_attempts})

    def _handle_review(self, state: LessonState, intent: ChildIntent) -> LessonState:
        """Child responded to review → farewell."""
        return state.model_copy(update={"stage": LessonStage.FAREWELL})

    # --- Handlers for auto-transition states ---

    def _auto_feedback(self, state: LessonState) -> LessonState:
        completed = list(state.completed_words)
        if state.current_word and state.current_word not in completed:
            completed.append(state.current_word)

        if state.has_next_word:
            return state.model_copy(
                update={
                    "stage": LessonStage.INTRODUCE_WORD,
                    "current_word_index": state.current_word_index + 1,
                    "completed_words": completed,
                    "attempts": 0,
                    "feedback_type": None,
                    "exercise_type": None,
                }
            )

        # Last word → go to review instead of directly to farewell
        return state.model_copy(
            update={
                "stage": LessonStage.REVIEW,
                "completed_words": completed,
            }
        )

    def _auto_farewell(self, state: LessonState) -> LessonState:
        return state.model_copy(update={"stage": LessonStage.COMPLETED})

    # --- Dispatch tables ---

    _handlers = {
        LessonStage.GREETING: _handle_greeting,
        LessonStage.INTRODUCE_WORD: _handle_introduce_word,
        LessonStage.REPEAT_WORD: _handle_repeat_word,
        LessonStage.EXERCISE: _handle_exercise,
        LessonStage.REVIEW: _handle_review,
    }

    _auto_stages = {
        LessonStage.FEEDBACK: _auto_feedback,
        LessonStage.FAREWELL: _auto_farewell,
    }
