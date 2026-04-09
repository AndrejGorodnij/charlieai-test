from pydantic import BaseModel

from app.models.state import ExerciseType


class ExerciseDefinition(BaseModel):
    exercise_type: ExerciseType
    prompt_hint: str
    accept_patterns: list[str]


WORD_EXERCISES: dict[str, ExerciseDefinition] = {
    "cat": ExerciseDefinition(
        exercise_type=ExerciseType.QUESTION,
        prompt_hint="Ask what sound a cat makes",
        accept_patterns=["meow", "mew", "мяу"],
    ),
    "dog": ExerciseDefinition(
        exercise_type=ExerciseType.CHOICE,
        prompt_hint="Ask if a dog is an animal or a fruit",
        accept_patterns=["animal"],
    ),
    "bird": ExerciseDefinition(
        exercise_type=ExerciseType.REPEAT,
        prompt_hint="Ask the child to say the word bird",
        accept_patterns=["bird"],
    ),
    "fish": ExerciseDefinition(
        exercise_type=ExerciseType.CHOICE,
        prompt_hint="Ask if a fish lives in water or in a tree",
        accept_patterns=["water"],
    ),
    "frog": ExerciseDefinition(
        exercise_type=ExerciseType.QUESTION,
        prompt_hint="Ask what color a frog usually is",
        accept_patterns=["green", "зелений", "зелена"],
    ),
}

DEFAULT_WORDS = ["cat", "dog", "bird"]


def get_exercise(word: str) -> ExerciseDefinition:
    """Get exercise definition for a word. Falls back to REPEAT if word is unknown."""
    return WORD_EXERCISES.get(
        word.lower(),
        ExerciseDefinition(
            exercise_type=ExerciseType.REPEAT,
            prompt_hint=f"Ask the child to say the word {word}",
            accept_patterns=[word.lower()],
        ),
    )
