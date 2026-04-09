"""Interactive CLI for testing Charlie AI lessons."""

import asyncio
import sys

from app.engine.lesson_engine import LessonEngine
from app.engine.state_machine import StateMachine
from app.llm.service import LLMService
from app.models.exercises import DEFAULT_WORDS
from app.store.session_store import SessionStore


def print_charlie(text: str) -> None:
    print(f"\n  🦊 Charlie: {text}\n")


def print_status(state) -> None:
    word = state.current_word or "—"
    print(f"  [{state.stage.value}] word: {word} | progress: {state.progress}")


async def main() -> None:
    words = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_WORDS
    print(f"\n=== Charlie AI Lesson ===")
    print(f"Words: {', '.join(words)}")
    print(f"Type your answers. Empty line = silence. Ctrl+C to quit.\n")

    engine = LessonEngine(
        llm_service=LLMService(),
        session_store=SessionStore(),
        state_machine=StateMachine(),
    )

    session_id, greeting, state = await engine.start_lesson(
        word_list=words, child_name=None
    )
    print_charlie(greeting)
    print_status(state)

    while not state.is_finished:
        try:
            child_input = input("  You: ")
        except (KeyboardInterrupt, EOFError):
            print("\n\nBye! 👋")
            break

        response, state = await engine.handle_message(session_id, child_input)
        print_charlie(response)
        print_status(state)

    if state.is_finished:
        print("\n✅ Lesson completed!\n")


if __name__ == "__main__":
    asyncio.run(main())
