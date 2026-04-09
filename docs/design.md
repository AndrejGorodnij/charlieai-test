# Charlie AI — System Design

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Layer                      │
│         /lesson/start  /lesson/message               │
└──────────────┬──────────────────┬────────────────────┘
               │                  │
               ▼                  ▼
┌──────────────────────────────────────────────────────┐
│                  LessonEngine                        │
│  Orchestrates the lesson: receives child input,      │
│  delegates to StateMachine + LLMService,             │
│  returns Charlie's response.                         │
└──────┬─────────────┬────────────────┬────────────────┘
       │             │                │
       ▼             ▼                ▼
┌────────────┐ ┌───────────┐ ┌─────────────────┐
│ State      │ │ LLM       │ │ Session         │
│ Machine    │ │ Service   │ │ Store           │
│            │ │           │ │                 │
│ States,    │ │ Groq API, │ │ In-memory dict  │
│ transitions│ │ prompts,  │ │ of LessonState  │
│ guards     │ │ parsing   │ │                 │
└────────────┘ └───────────┘ └─────────────────┘
```

**Data flow for each message:**

```
Child text
    │
    ▼
LessonEngine.handle_message(session_id, text)
    │
    ├── 1. Load LessonState from SessionStore
    │
    ├── 2. Pre-process input (empty? → mark as silence)
    │
    ├── 3. If state needs LLM evaluation (EXERCISE):
    │       └── LLMService.evaluate_and_respond(state, text)
    │           ├── Builds prompt from state context
    │           ├── Calls Groq API
    │           ├── Parses structured JSON response
    │           └── Returns LLMResult(response_text, child_intent)
    │
    ├── 4. If state auto-advances (GREETING, INTRODUCE_WORD, FAREWELL):
    │       └── LLMService.generate_response(state)
    │           └── Generates Charlie's line for this state
    │
    ├── 5. StateMachine.transition(state, child_intent)
    │       ├── Applies transition rules
    │       ├── Updates state (next word, next exercise, attempt++)
    │       └── Returns updated LessonState
    │
    ├── 6. Save updated LessonState to SessionStore
    │
    └── 7. Return response to API layer
```

---

## 2. State Machine Design

### 2.1 States

```
GREETING ──→ INTRODUCE_WORD ──→ EXERCISE ──→ FEEDBACK
                   ▲                             │
                   │         ┌───────────────────┘
                   │         │
                   │    [more words?]
                   │     yes │    no
                   │         │     │
                   └─────────┘     ▼
                              FAREWELL ──→ COMPLETED
```

### 2.2 Transitions Table

| From | Event | Guard | To | Side Effect |
|---|---|---|---|---|
| `GREETING` | `child_replied` | — | `INTRODUCE_WORD` | Set `current_word_index = 0` |
| `INTRODUCE_WORD` | `auto` | — | `EXERCISE` | Select exercise type for current word |
| `EXERCISE` | `correct_answer` | — | `FEEDBACK` | Set `feedback_type = positive` |
| `EXERCISE` | `wrong_answer` | `attempts < 3` | `EXERCISE` | Increment `attempts` |
| `EXERCISE` | `wrong_answer` | `attempts >= 3` | `FEEDBACK` | Set `feedback_type = give_answer` |
| `EXERCISE` | `partial_answer` | `attempts < 3` | `EXERCISE` | Increment `attempts` |
| `EXERCISE` | `off_topic` | — | `EXERCISE` | Increment `attempts` (redirect) |
| `EXERCISE` | `silence` | `attempts < 3` | `EXERCISE` | Increment `attempts` |
| `EXERCISE` | `silence` | `attempts >= 3` | `FEEDBACK` | Set `feedback_type = give_answer` |
| `FEEDBACK` | `auto` | `has_next_word` | `INTRODUCE_WORD` | Advance `current_word_index`, reset `attempts` |
| `FEEDBACK` | `auto` | `!has_next_word` | `FAREWELL` | — |
| `FAREWELL` | `auto` | — | `COMPLETED` | Mark session finished |

### 2.3 Events (child_intent enum)

```python
class ChildIntent(str, Enum):
    CORRECT_ANSWER = "correct_answer"
    WRONG_ANSWER = "wrong_answer"
    PARTIAL_ANSWER = "partial_answer"
    OFF_TOPIC = "off_topic"
    SILENCE = "silence"
    CHILD_REPLIED = "child_replied"  # generic, for GREETING
```

---

## 3. Data Models

### 3.1 LessonState

```python
class LessonState:
    session_id: str                  # UUID
    words: list[str]                 # ["cat", "dog", "bird"]
    current_word_index: int          # 0..len(words)-1
    current_state: LessonStage       # FSM state enum
    current_exercise: ExerciseType   # REPEAT / QUESTION / CHOICE
    attempts: int                    # 0..3 for current exercise
    feedback_type: FeedbackType      # POSITIVE / GIVE_ANSWER
    conversation_history: list[Message]  # for LLM context
    child_name: str | None           # extracted from greeting if provided
    completed_words: list[str]       # words already done
    created_at: datetime
```

### 3.2 LessonStage

```python
class LessonStage(str, Enum):
    GREETING = "greeting"
    INTRODUCE_WORD = "introduce_word"
    EXERCISE = "exercise"
    FEEDBACK = "feedback"
    FAREWELL = "farewell"
    COMPLETED = "completed"
```

### 3.3 ExerciseType

```python
class ExerciseType(str, Enum):
    REPEAT = "repeat"       # "Can you say CAT?"
    QUESTION = "question"   # "What sound does a cat make?"
    CHOICE = "choice"       # "Is a cat an animal or a fruit?"
```

### 3.4 Exercise Definitions

Exercises are defined per-word as data, not code:

```python
WORD_EXERCISES = {
    "cat": {
        "type": ExerciseType.QUESTION,
        "prompt_hint": "Ask what sound a cat makes",
        "accept_patterns": ["meow", "mew", "мяу"],
    },
    "dog": {
        "type": ExerciseType.CHOICE,
        "prompt_hint": "Ask if a dog is an animal or a fruit",
        "accept_patterns": ["animal"],
    },
    "bird": {
        "type": ExerciseType.REPEAT,
        "prompt_hint": "Ask the child to say the word bird",
        "accept_patterns": ["bird"],
    },
}
```

> `accept_patterns` is a soft hint for the LLM evaluator, not a rigid regex matcher. The LLM decides correctness using these as guidance.

---

## 4. API Contracts

### 4.1 POST /lesson/start

**Request:**
```json
{
    "word_list": ["cat", "dog", "bird"],  // optional, defaults to preset
    "child_name": "Марія"                 // optional
}
```

**Response:**
```json
{
    "session_id": "uuid-here",
    "charlie_response": "Hi there! I'm Charlie the fox! Ready to learn some cool words today?",
    "lesson_state": {
        "stage": "greeting",
        "current_word": null,
        "progress": "0/3",
        "is_finished": false
    }
}
```

### 4.2 POST /lesson/message

**Request:**
```json
{
    "session_id": "uuid-here",
    "text": "meow!"
}
```

**Response:**
```json
{
    "charlie_response": "Yes! Cats say meow! You're so smart! 🎉",
    "lesson_state": {
        "stage": "feedback",
        "current_word": "cat",
        "progress": "1/3",
        "is_finished": false
    }
}
```

### 4.3 GET /lesson/{session_id}/status

**Response:**
```json
{
    "session_id": "uuid-here",
    "stage": "exercise",
    "current_word": "dog",
    "progress": "1/3",
    "is_finished": false
}
```

### 4.4 Error Responses

```json
{
    "detail": "Session not found"       // 404
}
{
    "detail": "Lesson already completed" // 400
}
```

---

## 5. LLM Prompt Design

### 5.1 System Prompt (constant across all calls)

```
You are Charlie — an 8-year-old fox from London.
You are teaching English to a young child (age 4-8).

PERSONALITY:
- Playful, kind, enthusiastic
- You speak in short, simple sentences (max 2 sentences per reply)
- You use simple words (A1/pre-A1 level)
- You never say "wrong" or "incorrect" — instead you help and encourage
- You celebrate every success with enthusiasm

RULES:
- Stay in character as Charlie the fox at all times
- If the child speaks Ukrainian, respond in English but show you understood
- Never discuss topics inappropriate for children
- Never break the lesson flow — always gently guide back to the task
- Keep responses under 30 words
```

### 5.2 State-specific User Prompts

Each state builds a different user prompt:

**GREETING:**
```
Generate a greeting for the child.
{if child_name: "The child's name is {child_name}."}
Introduce yourself and ask if they're ready to learn some words today.
Respond with JSON: {"response_text": "..."}
```

**INTRODUCE_WORD:**
```
Introduce the word "{word}" to the child.
Give a short, fun explanation of what it means.
Respond with JSON: {"response_text": "..."}
```

**EXERCISE:**
```
Current word: "{word}"
Exercise type: {exercise_type}
Task hint: {prompt_hint}
Child's answer: "{child_text}"
Attempt: {attempt}/3
Acceptable answers include: {accept_patterns}

Evaluate the child's response and reply as Charlie.
If the answer is empty or blank, gently encourage and repeat the question.
If the answer is off-topic, briefly react and redirect to the task.

Respond with JSON:
{
    "response_text": "...",
    "child_intent": "correct_answer|wrong_answer|partial_answer|off_topic|silence"
}
```

**FEEDBACK (positive):**
```
The child got the word "{word}" correct!
Celebrate briefly and say you're moving to the next word.
Respond with JSON: {"response_text": "..."}
```

**FEEDBACK (give_answer):**
```
The child struggled with "{word}" after 3 attempts.
Kindly give the answer yourself, praise them for trying, and say you're moving on.
Respond with JSON: {"response_text": "..."}
```

**FAREWELL:**
```
The lesson is over. The child learned these words: {completed_words}.
Say goodbye warmly, praise their effort, and encourage them to come back.
Respond with JSON: {"response_text": "..."}
```

### 5.3 LLM Response Parsing

- Parse JSON from LLM response
- If JSON parsing fails → retry once with stricter prompt
- If retry fails → use fallback response from `FALLBACK_RESPONSES[current_state]`

### 5.4 Conversation History Management

- Send last 6 messages (3 pairs) as conversation context to maintain coherence
- System prompt is always included
- State-specific prompt replaces (not appends to) previous state prompts

---

## 6. Component Interfaces

### 6.1 LessonEngine

```python
class LessonEngine:
    async def start_lesson(self, word_list: list[str], child_name: str | None) -> tuple[str, LessonResponse]
    async def handle_message(self, session_id: str, text: str) -> LessonResponse
```

### 6.2 StateMachine

```python
class StateMachine:
    def transition(self, state: LessonState, event: ChildIntent) -> LessonState
    def get_auto_transitions(self, state: LessonState) -> LessonState | None
```

No async, no I/O. Pure function over state.

### 6.3 LLMService

```python
class LLMService:
    async def generate_response(self, state: LessonState) -> LLMResult
    async def evaluate_and_respond(self, state: LessonState, child_text: str) -> LLMResult
```

### 6.4 SessionStore

```python
class SessionStore:
    def create(self, state: LessonState) -> str  # returns session_id
    def get(self, session_id: str) -> LessonState | None
    def update(self, session_id: str, state: LessonState) -> None
```

---

## 7. File Structure

```
charlie-ai/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, endpoints
│   ├── config.py               # Settings (Groq API key, model, etc.)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py          # Pydantic: API request/response
│   │   ├── state.py            # LessonState, LessonStage, ExerciseType, ChildIntent
│   │   └── exercises.py        # WORD_EXERCISES data definitions
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── lesson_engine.py    # LessonEngine orchestrator
│   │   └── state_machine.py    # StateMachine transitions
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── service.py          # LLMService (Groq calls)
│   │   ├── prompts.py          # System prompt + state prompt builders
│   │   └── fallbacks.py        # Fallback responses per state
│   └── store/
│       ├── __init__.py
│       └── session_store.py    # In-memory session storage
├── tests/
│   ├── __init__.py
│   ├── test_state_machine.py   # Pure FSM tests (no LLM)
│   ├── test_engine.py          # Engine tests with mocked LLM
│   └── test_api.py             # Integration tests via TestClient
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 8. Technology Choices

| Component | Choice | Rationale |
|---|---|---|
| Framework | FastAPI | Async, auto-docs, Pydantic integration |
| LLM Provider | Groq | Free tier, fast inference, specified in task |
| LLM Model | `llama-3.3-70b-versatile` | Best reasoning on Groq free tier |
| HTTP client | `httpx` | Async-native, used by groq SDK |
| Validation | Pydantic v2 | Already bundled with FastAPI |
| Testing | pytest + pytest-asyncio | Standard for async Python |

---

## 9. Error Handling Strategy

| Failure | Handling |
|---|---|
| Groq API timeout/error | Return fallback Charlie response, do NOT advance state |
| JSON parse failure from LLM | Retry once with stricter prompt; if fails → fallback |
| Session not found | Return 404 |
| Message to completed lesson | Return 400 |
| Invalid word list (empty) | Return 422 validation error |
