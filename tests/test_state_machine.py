"""Tests for the StateMachine — pure logic, no LLM, no I/O."""

import pytest

from app.engine.state_machine import MAX_ATTEMPTS, StateMachine
from app.models.state import (
    ChildIntent,
    ExerciseType,
    FeedbackType,
    LessonStage,
    LessonState,
)


@pytest.fixture
def sm():
    return StateMachine()


@pytest.fixture
def greeting_state():
    return LessonState(
        session_id="test-1",
        words=["cat", "dog", "bird"],
        stage=LessonStage.GREETING,
    )


@pytest.fixture
def introduce_state():
    return LessonState(
        session_id="test-1",
        words=["cat", "dog", "bird"],
        stage=LessonStage.INTRODUCE_WORD,
        current_word_index=0,
    )


@pytest.fixture
def exercise_state():
    return LessonState(
        session_id="test-1",
        words=["cat", "dog", "bird"],
        stage=LessonStage.EXERCISE,
        current_word_index=0,
        exercise_type=ExerciseType.QUESTION,
        attempts=0,
    )


class TestGreetingTransitions:
    def test_child_reply_moves_to_introduce_word(self, sm, greeting_state):
        new_state = sm.transition(greeting_state, ChildIntent.CHILD_REPLIED)
        assert new_state.stage == LessonStage.INTRODUCE_WORD
        assert new_state.current_word_index == 0


class TestIntroduceWordTransitions:
    def test_child_reply_moves_to_exercise(self, sm, introduce_state):
        new_state = sm.transition(introduce_state, ChildIntent.CHILD_REPLIED)
        assert new_state.stage == LessonStage.EXERCISE
        assert new_state.exercise_type is not None
        assert new_state.attempts == 0

    def test_exercise_type_matches_word(self, sm, introduce_state):
        new_state = sm.transition(introduce_state, ChildIntent.CHILD_REPLIED)
        # "cat" exercise is QUESTION type
        assert new_state.exercise_type == ExerciseType.QUESTION


class TestExerciseTransitions:
    def test_correct_answer_moves_to_feedback_positive(self, sm, exercise_state):
        new_state = sm.transition(exercise_state, ChildIntent.CORRECT_ANSWER)
        assert new_state.stage == LessonStage.FEEDBACK
        assert new_state.feedback_type == FeedbackType.POSITIVE

    def test_wrong_answer_increments_attempts(self, sm, exercise_state):
        new_state = sm.transition(exercise_state, ChildIntent.WRONG_ANSWER)
        assert new_state.stage == LessonStage.EXERCISE
        assert new_state.attempts == 1

    def test_max_attempts_moves_to_feedback_give_answer(self, sm, exercise_state):
        state = exercise_state.model_copy(update={"attempts": MAX_ATTEMPTS - 1})
        new_state = sm.transition(state, ChildIntent.WRONG_ANSWER)
        assert new_state.stage == LessonStage.FEEDBACK
        assert new_state.feedback_type == FeedbackType.GIVE_ANSWER

    def test_silence_increments_attempts(self, sm, exercise_state):
        new_state = sm.transition(exercise_state, ChildIntent.SILENCE)
        assert new_state.stage == LessonStage.EXERCISE
        assert new_state.attempts == 1

    def test_off_topic_increments_attempts(self, sm, exercise_state):
        new_state = sm.transition(exercise_state, ChildIntent.OFF_TOPIC)
        assert new_state.stage == LessonStage.EXERCISE
        assert new_state.attempts == 1

    def test_partial_answer_increments_attempts(self, sm, exercise_state):
        new_state = sm.transition(exercise_state, ChildIntent.PARTIAL_ANSWER)
        assert new_state.stage == LessonStage.EXERCISE
        assert new_state.attempts == 1


class TestAutoTransitions:
    def test_feedback_with_next_word_moves_to_introduce(self, sm):
        state = LessonState(
            session_id="test-1",
            words=["cat", "dog"],
            stage=LessonStage.FEEDBACK,
            current_word_index=0,
            feedback_type=FeedbackType.POSITIVE,
        )
        new_state = sm.apply_auto_transitions(state)
        # FEEDBACK → INTRODUCE_WORD (stops here — waits for child input)
        assert new_state.stage == LessonStage.INTRODUCE_WORD
        assert new_state.current_word_index == 1
        assert "cat" in new_state.completed_words

    def test_feedback_last_word_moves_to_completed(self, sm):
        state = LessonState(
            session_id="test-1",
            words=["cat"],
            stage=LessonStage.FEEDBACK,
            current_word_index=0,
            feedback_type=FeedbackType.POSITIVE,
        )
        new_state = sm.apply_auto_transitions(state)
        # FEEDBACK → FAREWELL → COMPLETED
        assert new_state.stage == LessonStage.COMPLETED
        assert new_state.is_finished
        assert "cat" in new_state.completed_words


class TestFullLessonFlow:
    def test_complete_lesson_all_correct(self, sm):
        """Simulate a full lesson with all correct answers."""
        state = LessonState(
            session_id="test-1",
            words=["cat", "dog"],
            stage=LessonStage.GREETING,
        )

        # Greeting → Introduce Word
        state = sm.transition(state, ChildIntent.CHILD_REPLIED)
        assert state.stage == LessonStage.INTRODUCE_WORD

        # Introduce → Exercise (child reacts)
        state = sm.transition(state, ChildIntent.CHILD_REPLIED)
        assert state.stage == LessonStage.EXERCISE
        assert state.current_word == "cat"

        # Correct answer → Feedback
        state = sm.transition(state, ChildIntent.CORRECT_ANSWER)
        assert state.stage == LessonStage.FEEDBACK

        # Auto: Feedback → Introduce Word (dog)
        state = sm.apply_auto_transitions(state)
        assert state.stage == LessonStage.INTRODUCE_WORD
        assert state.current_word == "dog"

        # Introduce → Exercise (child reacts)
        state = sm.transition(state, ChildIntent.CHILD_REPLIED)
        assert state.stage == LessonStage.EXERCISE

        # Correct answer → Feedback
        state = sm.transition(state, ChildIntent.CORRECT_ANSWER)
        assert state.stage == LessonStage.FEEDBACK

        # Auto: Feedback → Farewell → Completed
        state = sm.apply_auto_transitions(state)
        assert state.stage == LessonStage.COMPLETED
        assert state.completed_words == ["cat", "dog"]

    def test_lesson_with_failures(self, sm):
        """Simulate a lesson where child fails max attempts on first word."""
        state = LessonState(
            session_id="test-1",
            words=["cat"],
            stage=LessonStage.EXERCISE,
            current_word_index=0,
            exercise_type=ExerciseType.QUESTION,
            attempts=0,
        )

        # 3 wrong answers
        for i in range(MAX_ATTEMPTS - 1):
            state = sm.transition(state, ChildIntent.WRONG_ANSWER)
            assert state.stage == LessonStage.EXERCISE
            assert state.attempts == i + 1

        # Final wrong answer → give answer feedback
        state = sm.transition(state, ChildIntent.WRONG_ANSWER)
        assert state.stage == LessonStage.FEEDBACK
        assert state.feedback_type == FeedbackType.GIVE_ANSWER

        # Auto: Feedback → Farewell → Completed
        state = sm.apply_auto_transitions(state)
        assert state.stage == LessonStage.COMPLETED
