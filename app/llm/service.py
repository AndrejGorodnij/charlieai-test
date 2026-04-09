import json
import logging

from groq import AsyncGroq

from app.llm.fallbacks import FALLBACK_RESPONSES
from app.llm.prompts import (
    SYSTEM_PROMPT,
    build_evaluate_prompt,
    build_greeting_prompt,
    build_turn_prompt,
)
from app.models.state import ChildIntent, LessonState
from app.models.turn import TurnContext

logger = logging.getLogger(__name__)


class LLMService:
    """Groq-backed implementation of LLMServiceProtocol."""

    def __init__(
        self, client: AsyncGroq | None = None, model: str | None = None
    ) -> None:
        if client is not None:
            self._client = client
            self._model = model or "llama-3.3-70b-versatile"
        else:
            from app.config import settings

            self._client = AsyncGroq(api_key=settings.groq_api_key)
            self._model = model or settings.groq_model

    async def generate_greeting(self, state: LessonState) -> str:
        """Generate Charlie's initial greeting."""
        prompt = build_greeting_prompt(state)
        messages = self._build_messages(state, prompt)

        try:
            data = await self._call_llm_json(messages)
            return data.get("response_text", "").strip() or self._fallback("greeting")
        except Exception:
            logger.exception("LLM call failed (greeting)")
            return self._fallback("greeting")

    async def evaluate_intent(
        self, state: LessonState, child_text: str
    ) -> ChildIntent:
        """Classify the child's answer — returns intent only, no response text."""
        if not child_text or not child_text.strip():
            return ChildIntent.SILENCE

        prompt = build_evaluate_prompt(state, child_text)
        messages = self._build_messages(state, prompt)

        try:
            data = await self._call_llm_json(messages)
            raw = data.get("child_intent", "wrong_answer")
            return ChildIntent(raw)
        except (ValueError, Exception):
            logger.exception("LLM call failed (evaluate)")
            return ChildIntent.WRONG_ANSWER

    async def generate_turn_response(
        self, state: LessonState, turn: TurnContext
    ) -> str:
        """Generate Charlie's complete response for a turn — one call, one coherent reply."""
        prompt = build_turn_prompt(turn)
        messages = self._build_messages(state, prompt)

        try:
            data = await self._call_llm_json(messages)
            return data.get("response_text", "").strip() or self._fallback("default")
        except Exception:
            logger.exception("LLM call failed (turn response)")
            return self._fallback("default")

    # --- Private helpers ---

    async def _call_llm_json(self, messages: list[dict[str, str]]) -> dict:
        """Call LLM and return parsed JSON dict."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=200,
        )

        content = response.choices[0].message.content or ""
        return json.loads(content)

    def _build_messages(
        self, state: LessonState, user_prompt: str
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add recent conversation history (last 6 messages for context)
        for msg in state.conversation_history[-6:]:
            role = "assistant" if msg.role == "charlie" else "user"
            messages.append({"role": role, "content": msg.text})

        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _fallback(self, key: str) -> str:
        defaults = {
            "greeting": FALLBACK_RESPONSES.get("greeting", "Hi! I'm Charlie the fox! Ready to learn?"),
            "default": "Let's keep going! You're doing great!",
        }
        return defaults.get(key, "Let's keep going!")
