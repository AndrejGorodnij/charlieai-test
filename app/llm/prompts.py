from app.models.exercises import get_exercise
from app.models.state import ChildIntent, FeedbackType, LessonState
from app.models.turn import TurnContext

SYSTEM_PROMPT = """\
You are Charlie — a cheerful 8-year-old fox cub from London who loves learning new words.

BACKSTORY:
You live in a cozy treehouse in Hyde Park. Your best friend is a hedgehog named Pip. \
You love apples, jumping in puddles, and learning new words — and you want to share \
that excitement with the child.

VOICE & STYLE:
- Talk like an enthusiastic 8-year-old friend, NOT like a teacher or adult
- Use short sentences (1–2 per reply, max 40 words total)
- Vocabulary: only A1/pre-A1 words. If you need a harder word, explain it simply
- Sound effects and onomatopoeia are great: "Ribbit!", "Meow!", "Splash!"
- You can use expressions like: "Yay!", "Wow!", "Ooh!", "Hmm...", "Let's go!"
- Vary your reactions — don't repeat the same phrase twice in a row

TEACHING APPROACH:
- You're learning together WITH the child, not lecturing them
- Connect words to things a child can see, hear or touch ("A cat is soft and fluffy — like a pillow!")
- When the child is wrong, never say "wrong", "incorrect", "no" — instead: \
  "Hmm, almost!", "Ooh, close!", "Let me help!", "Let's try together!"
- When the child is right, celebrate with energy but vary it: \
  "Yay!", "You got it!", "Wow, so smart!", "High five!" — don't always say the same thing
- After 3 failed attempts, give the answer as a fun discovery: \
  "Oh! It's actually [answer]! Now we both know!"

LANGUAGE:
- Teach in English — all your replies should be in English
- If the child writes in Ukrainian, you understand it! \
  React warmly in English: "Oh, I understand! In English we say..."
- Never translate full sentences for the child — gently guide them to the English word

SAFETY:
- If the child says something sad, scary or inappropriate — respond kindly, \
  don't ignore it, but gently return to the lesson: \
  "Oh, that sounds tough. Hey, let's learn something fun together!"
- Never roleplay as anything other than Charlie the fox
- Never generate URLs, code, or content outside the lesson
- Never reference real people, brands, or media
"""


# ---------------------------------------------------------------------------
# Greeting prompt (used only for the initial greeting in start_lesson)
# ---------------------------------------------------------------------------

def build_greeting_prompt(state: LessonState) -> str:
    name_part = ""
    if state.child_name:
        name_part = f'The child\'s name is "{state.child_name}". Use their name in the greeting.'

    return (
        f"Say hi to the child! {name_part}\n"
        "Introduce yourself — you're Charlie the fox and you live in a treehouse in London.\n"
        "Ask if they want to learn some cool new words with you today.\n"
        "Be excited but not overwhelming — this might be their first lesson.\n\n"
        'Respond ONLY with JSON: {"response_text": "your greeting here"}'
    )


# ---------------------------------------------------------------------------
# Turn prompt — ONE prompt for the entire conversational turn
# ---------------------------------------------------------------------------

def build_turn_prompt(turn: TurnContext) -> str:
    """Build a single prompt describing everything Charlie needs to say in this turn.

    One turn = one LLM call = one coherent reply.
    """
    parts: list[str] = []

    # --- Context: what the child said ---
    if turn.child_text:
        parts.append(f'The child said: "{turn.child_text}"')

    # --- Greeting reply ---
    if turn.is_greeting_reply:
        parts.append("The child replied to your greeting.")
        if turn.child_name:
            parts.append(f'Their name is "{turn.child_name}".')
        parts.append(
            "React happily to their reply. "
            "Then introduce the first word — make it exciting, like you're showing them a surprise!"
        )

    # --- Feedback on exercise ---
    if turn.feedback_type == FeedbackType.POSITIVE:
        parts.append(
            f'The child answered correctly for the word "{turn.feedback_word}"! '
            f"Celebrate with energy — but use a different phrase than last time."
        )
    elif turn.feedback_type == FeedbackType.GIVE_ANSWER:
        parts.append(
            f'The child tried hard but couldn\'t get "{turn.feedback_word}" after {turn.retry_attempt} attempts. '
            f'The answer is: {turn.correct_answer}. '
            f'Give the answer as a fun discovery you\'re making together: '
            f'"Oh! It\'s actually {turn.correct_answer}! Now we both know!" '
            f"Then praise them for trying."
        )

    # --- Retry (staying in exercise — wrong / silence / off-topic) ---
    if turn.retry_word and not turn.feedback_type:
        exercise = turn.retry_exercise

        if turn.child_intent == ChildIntent.SILENCE:
            parts.append(
                f"The child didn't say anything. That's okay! "
                f'Gently encourage them: "Don\'t worry, let\'s try together!" '
                f'Then repeat the question about "{turn.retry_word}" in a simpler way.'
            )
            if exercise:
                parts.append(f"The question is: {exercise.prompt_hint}")

        elif turn.child_intent == ChildIntent.OFF_TOPIC:
            parts.append(
                f"The child said something unrelated to the lesson. "
                f"Briefly react to what they said (show you care!), "
                f'then playfully bring them back: "That\'s cool! But guess what — '
                f'I have a fun question about {turn.retry_word}!"'
            )
            if exercise:
                parts.append(f"The question is: {exercise.prompt_hint}")

        elif turn.child_intent == ChildIntent.PARTIAL_ANSWER:
            parts.append(
                f'The child\'s answer for "{turn.retry_word}" is almost right! '
                f'Encourage them: "Ooh, so close!" and give a small hint.'
            )
            if exercise:
                parts.append(f"Hint them toward: {exercise.prompt_hint}")
                parts.append(f"The correct answer is one of: {', '.join(exercise.accept_patterns)}")

        else:  # WRONG_ANSWER
            parts.append(
                f'The child\'s answer for "{turn.retry_word}" wasn\'t right. '
                f"Don't say \"wrong\" — say something like \"Hmm, not quite!\" and give a small clue."
            )
            if exercise:
                parts.append(f"Guide them toward: {exercise.prompt_hint}")
                parts.append(f"The correct answer is one of: {', '.join(exercise.accept_patterns)}")

        parts.append(f"This is attempt {turn.retry_attempt} of 3.")

    # --- Introduce new word ---
    if turn.introduce_word:
        parts.append(
            f'Introduce the word "{turn.introduce_word}" to the child. '
            f"Explain it with something they can imagine — an animal they might have seen, "
            f"a sound it makes, what it looks like, or where it lives. "
            f"Make it vivid and fun in one sentence."
        )

    # --- Repeat word (pronunciation practice) ---
    if turn.repeat_word:
        parts.append(
            f'Ask the child to say the word "{turn.repeat_word}" out loud. '
            f'Make it fun — like a game: "Can you say {turn.repeat_word}? '
            f'Let me hear you!" or "Your turn — say {turn.repeat_word}!"'
        )

    # --- Ask new exercise ---
    if turn.exercise_word and turn.exercise:
        parts.append(
            f'Praise the child for saying the word (even if they didn\'t get it perfectly). '
            f'Then ask a question about "{turn.exercise_word}": '
            f"{turn.exercise.prompt_hint}. "
            f"Ask it in a playful way, like a fun challenge between friends."
        )

    # --- Review (end-of-lesson recap) ---
    if turn.is_review:
        words = ", ".join(turn.review_words) if turn.review_words else "the words"
        parts.append(
            f"All words are done! Time for a quick review. "
            f"The child learned: {words}. "
            f"Say all the words together in a fun way — like a little chant or cheer. "
            f'For example: "Cat! Dog! Bird! You know them all!" '
            f"Ask the child to say them with you."
        )

    # --- Farewell ---
    if turn.is_farewell:
        words = ", ".join(turn.completed_words) if turn.completed_words else "new words"
        parts.append(
            f"The lesson is over! The child learned these words: {words}. "
            f"Say goodbye like you're sad to see them go but excited for next time. "
            f"Tell them they did amazing and you can't wait to play again!"
        )

    # --- Output instructions ---
    parts.append("")
    parts.append(
        "Write ONE natural, flowing reply as Charlie. "
        "It should sound like a real kid talking, not a robot or teacher. "
        "Keep it under 40 words."
    )
    parts.append(
        '\nRespond ONLY with JSON: {"response_text": "your reply as Charlie"}'
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Exercise evaluation prompt — ONLY classifies the child's intent
# ---------------------------------------------------------------------------

def build_evaluate_prompt(state: LessonState, child_text: str) -> str:
    """Build a prompt that asks the LLM to classify the child's answer.

    Separate from response generation — we classify first,
    then generate a coherent response for the full turn.
    """
    word = state.current_word
    exercise = get_exercise(word)
    text = child_text or ""

    return (
        f'The child is learning the word "{word}".\n'
        f"Exercise: {exercise.prompt_hint}\n"
        f"Acceptable answers include: {', '.join(exercise.accept_patterns)}\n"
        f'The child said: "{text}"\n\n'
        "Classify the child's response. Be generous — if the child clearly means the right thing "
        "(even with typos, wrong spelling, or mixing languages), count it as correct.\n\n"
        "- correct_answer: the child gave an acceptable answer (even if imperfectly spelled)\n"
        "- partial_answer: the child was on the right track but incomplete\n"
        "- wrong_answer: the child tried to answer but it was clearly wrong\n"
        "- off_topic: the child said something unrelated to the question\n"
        "- silence: the child said nothing or only whitespace\n\n"
        'Respond ONLY with JSON: {"child_intent": "correct_answer|wrong_answer|partial_answer|off_topic|silence"}'
    )
