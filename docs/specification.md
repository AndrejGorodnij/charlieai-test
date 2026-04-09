# Charlie AI — Lesson Engine Specification

## 1. Product Context

**Product:** Charlie AI — voice AI English teacher for children aged 4–8 on the All Right EdTech platform.

**Scope of this task:** Core lesson logic only. No voice/TTS/STT. Text-in → text-out service.

**Character:** Charlie — an 8-year-old fox from London. Playful, kind, speaks in short simple sentences, encourages the child.

---

## 2. Functional Requirements

### FR-1: Lesson Lifecycle

- **FR-1.1:** The system SHALL create a lesson session with a predefined word list (3–5 English words).
- **FR-1.2:** Each lesson SHALL follow a fixed flow: Greeting → Word Exercises → Farewell.
- **FR-1.3:** The lesson flow SHALL be controlled by a deterministic state machine, NOT by the LLM.
- **FR-1.4:** The system SHALL track lesson progress: current word, current exercise type, attempt count, completed words.

### FR-2: Lesson States

The lesson SHALL transition through these states in order:

| State | Description |
|---|---|
| `GREETING` | Charlie introduces himself, asks the child's name or says hello. Transitions to first word after one exchange. |
| `INTRODUCE_WORD` | Charlie presents the current word (e.g., "Today we'll learn the word CAT! A cat is a small fluffy animal."). Auto-transitions to `EXERCISE`. |
| `EXERCISE` | Charlie asks the child to interact with the word (repeat it, answer a question about it, use it). Waits for child input. |
| `FEEDBACK` | Engine evaluates the child's response and provides feedback. Transitions to next word's `INTRODUCE_WORD` or to `FAREWELL` if all words are done. |
| `FAREWELL` | Charlie says goodbye, praises the child for the lesson. Session ends. |

### FR-3: Exercise Types

For each word, the engine SHALL run one or more exercises from:

- **Repeat:** "Can you say CAT?" — child should say the word back.
- **Question:** "What sound does a cat make?" — simple comprehension question.
- **Choice:** "Is a cat an animal or a fruit?" — binary/simple choice.

The engine selects the exercise type. One exercise per word is sufficient.

### FR-4: Child Input Handling

- **FR-4.1 (Empty input):** If the child sends empty or whitespace-only text, Charlie SHALL gently repeat the task with encouragement. This counts as an attempt.
- **FR-4.2 (Off-topic):** If the child says something unrelated to the lesson, Charlie SHALL briefly acknowledge it and redirect to the current task.
- **FR-4.3 (Partial/incorrect answer):** Charlie SHALL NOT say "wrong" or "incorrect". Instead, Charlie gives a hint and asks again.
- **FR-4.4 (Correct answer):** Charlie celebrates and the engine advances to the next word or state.
- **FR-4.5 (Max attempts):** After 3 failed attempts on one exercise, Charlie SHALL provide the correct answer himself, praise the effort, and move on.

### FR-5: LLM Integration

- **FR-5.1:** The system SHALL use Groq API as the LLM provider.
- **FR-5.2:** The LLM SHALL only generate Charlie's dialogue text. It SHALL NOT control lesson flow or state transitions.
- **FR-5.3:** The system SHALL send structured context to the LLM: current state, current word, exercise type, child's input, attempt number.
- **FR-5.4:** The LLM SHALL return a structured response (JSON) containing: `response_text` (Charlie's reply), `child_understood` (boolean — did the child's input match the expected answer), `child_intent` (enum: `correct_answer`, `wrong_answer`, `off_topic`, `silence`, `partial_answer`).
- **FR-5.5:** Charlie's responses SHALL be max 2 sentences, use simple vocabulary (A1 level), and stay in character.

### FR-6: API Interface

- **FR-6.1:** `POST /lesson/start` — accepts optional `word_list` (defaults to predefined list), returns `session_id` and Charlie's greeting.
- **FR-6.2:** `POST /lesson/message` — accepts `session_id` and `text` (child's input), returns Charlie's response and lesson metadata (current word, progress, state).
- **FR-6.3:** `GET /lesson/{session_id}/status` — returns current lesson state and progress.

---

## 3. Non-Functional Requirements

- **NFR-1:** Response latency under 3 seconds (dependent on Groq API).
- **NFR-2:** Session state stored in-memory (no database required for MVP).
- **NFR-3:** The system SHALL gracefully handle LLM API failures with a fallback Charlie response (e.g., "Hmm, let me think... Can you say that again?").
- **NFR-4:** All prompts and persona definitions SHALL be separate from business logic (not hardcoded in engine code).

---

## 4. Out of Scope

- Voice input/output (STT/TTS)
- User authentication
- Persistent storage / database
- Frontend / UI
- Multi-language lesson content (lesson is in English; child may respond in Ukrainian — Charlie handles it gracefully but teaches in English)
- Analytics / reporting

---

## 5. Acceptance Criteria

1. A full lesson can be completed via API calls: start → multiple messages → farewell.
2. Charlie stays in character across the entire lesson.
3. Empty input, off-topic input, and wrong answers are handled gracefully without breaking the flow.
4. The state machine advances correctly through all words and states.
5. LLM failure does not crash the service — fallback responses are provided.
6. The project runs with `docker compose up` or `pip install + uvicorn` and a Groq API key.
