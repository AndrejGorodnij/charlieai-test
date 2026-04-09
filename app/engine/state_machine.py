from app.models.exercises import get_exercise
from app.models.state import (
    ChildIntent,
    FeedbackType,
    LessonStage,
    LessonState,
)

MAX_ATTEMPTS = 3


class StateMachine:
    """Pure deterministic state machine. No I/O, no side effects."""

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

    # --- Handlers for child-input states ---

    def _handle_greeting(self, state: LessonState, intent: ChildIntent) -> LessonState:
        return state.model_copy(
            update={
                "stage": LessonStage.INTRODUCE_WORD,
                "current_word_index": 0,
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

    # --- Handler for INTRODUCE_WORD (waits for child input) ---

    def _handle_introduce_word(
        self, state: LessonState, intent: ChildIntent
    ) -> LessonState:
        """Child reacted to word introduction → move to exercise."""
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

        return state.model_copy(
            update={
                "stage": LessonStage.FAREWELL,
                "completed_words": completed,
            }
        )

    def _auto_farewell(self, state: LessonState) -> LessonState:
        return state.model_copy(update={"stage": LessonStage.COMPLETED})

    # --- Dispatch tables ---

    _handlers = {
        LessonStage.GREETING: _handle_greeting,
        LessonStage.INTRODUCE_WORD: _handle_introduce_word,
        LessonStage.EXERCISE: _handle_exercise,
    }

    _auto_stages = {
        LessonStage.FEEDBACK: _auto_feedback,
        LessonStage.FAREWELL: _auto_farewell,
    }
