# Charlie AI — Lesson Engine

Ядро голосового AI-вчителя англійської для дітей 4–8 років. Сервіс приймає текст (що дитина сказала), керує flow міні-уроку і генерує відповідь персонажа Charlie через LLM.

**Charlie** — лисеня 8 років з Лондона, грайливий і добрий, говорить коротко і просто, підбадьорює.

> Голосова частина (STT/TTS) не входить в scope — тільки текстове ядро.

---

## Як запустити

### Передумови

- Python 3.11+
- Безкоштовний API-ключ Groq ([console.groq.com](https://console.groq.com) → API Keys → Create)

### Локально

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Вставити GROQ_API_KEY в .env
```

**Інтерактивний CLI** (найшвидший спосіб побачити роботу):

```bash
python cli.py                    # слова за замовчуванням: cat, dog, bird
python cli.py frog fish cat      # кастомний набір слів
```

**API-сервер:**

```bash
uvicorn app.main:app --reload
# Swagger UI: http://localhost:8000/docs
```

### Docker

```bash
cp .env.example .env
# Вставити GROQ_API_KEY в .env

docker compose up --build
```

### Тести

```bash
GROQ_API_KEY=test-key pytest -v
```

Всі 31 тест працюють без реального API-ключа — LLM замінюється на mock через протоколи.

---

## Як влаштований flow уроку

### Хто керує flow

**State machine** (`StateMachine`) — детермінована, без I/O, без побічних ефектів. Це вона вирішує, який стан наступний, скільки спроб залишилось, коли закінчити урок. LLM **не приймає жодних рішень** щодо flow — тільки генерує текст в рамках вже прийнятого рішення.

### Стани

```
GREETING ──→ INTRODUCE_WORD ──→ EXERCISE ──→ FEEDBACK ──→ INTRODUCE_WORD (наступне слово)
   │              │                  │           │
   │         чекає реакції      чекає відповідь   │
   │           дитини             дитини      auto-transition
   │                                               │
  чекає                                     якщо слова скінчились:
  відповідь                                        │
  дитини                                      FAREWELL ──→ COMPLETED
```

**Стани, що чекають input дитини** (перехід тільки після повідомлення):
- `GREETING` — Charlie вітається, дитина відповідає
- `INTRODUCE_WORD` — Charlie представляє нове слово, дитина реагує
- `EXERCISE` — Charlie ставить питання, дитина відповідає

**Auto-transition стани** (переходять автоматично, без очікування):
- `FEEDBACK` → переходить до `INTRODUCE_WORD` наступного слова або `FAREWELL`
- `FAREWELL` → `COMPLETED`

### Приклад діалогу

```
🦊 Charlie: Hi! I'm Charlie the fox! Ready to learn some words?
👦 Дитина:  Yes!                                                   [GREETING → INTRODUCE_WORD]

🦊 Charlie: Awesome! Meet FROG — a little green animal that jumps!
👦 Дитина:  Cool!                                                  [INTRODUCE_WORD → EXERCISE]

🦊 Charlie: What color is a frog?
👦 Дитина:  I like pizza                                           [OFF_TOPIC — залишаємось]

🦊 Charlie: Pizza is yummy! But what color is a frog?
👦 Дитина:  Green!                                                 [CORRECT → FEEDBACK → INTRODUCE_WORD]

🦊 Charlie: Yes! Now meet FISH — it lives in water and can swim!
👦 Дитина:  Ok                                                     [INTRODUCE_WORD → EXERCISE]

🦊 Charlie: Does a fish live in water or in a tree?
👦 Дитина:  Water!                                                 [CORRECT → FEEDBACK → FAREWELL]

🦊 Charlie: Amazing! You learned frog and fish! See you next time!
```

---

## Як працює LLM

### Принцип: одне повідомлення дитини → один виклик LLM → одна зв'язна відповідь

Engine **спочатку** визначає всі переходи станів (через state machine), **потім** будує `TurnContext` — повний опис того, що сталося в цьому ході — і робить **один** виклик LLM для генерації зв'язної відповіді.

Це означає, що коли дитина відповідає правильно і урок переходить до наступного слова, Charlie говорить одне цілісне повідомлення ("Yay! Now meet FISH..."), а не склейку з 3-4 окремих фрагментів.

### Три типи LLM-викликів

| Метод | Коли | Що робить |
|---|---|---|
| `generate_greeting()` | Старт уроку | Генерує привітання Charlie |
| `evaluate_intent()` | Дитина відповіла на вправу | **Тільки класифікує** відповідь (correct / wrong / off_topic / silence / partial). Не генерує текст |
| `generate_turn_response()` | Кожне повідомлення дитини | Генерує одну зв'язну відповідь Charlie для всього, що сталось в цьому ході |

### Prompt engineering: як побудований персонаж

System prompt складається з кількох шарів, кожен з яких вирішує конкретну проблему:

**Backstory** — Charlie живе в будиночку на дереві в Hyde Park, його друг — їжачок Pip, він любить яблука і стрибати по калюжах. Це не декорація: backstory дає LLM матеріал для природних, різноманітних реплік замість одноманітних "Good job!".

**Voice & Style** — замість абстрактного "speak simply" промпт дає конкретні інструменти:
- Звуконаслідування: "Ribbit!", "Meow!", "Splash!"
- Вигуки: "Yay!", "Wow!", "Ooh!", "Hmm..."
- Обмеження: 1–2 речення, до 40 слів, лексика A1/pre-A1
- Заборона повторювати ту саму фразу двічі поспіль

**Teaching approach** — педагогічні принципи, адаптовані для LLM:
- Charlie вчиться **разом** з дитиною, а не поводиться як вчитель зверху
- Слова пов'язуються з тактильним/візуальним досвідом: "A cat is soft and fluffy — like a pillow!"
- Ніколи "wrong"/"incorrect"/"no" — замість цього конкретні фрази: "Hmm, almost!", "Ooh, close!", "Let me help!"
- Після 3 невдач — подача відповіді як спільне відкриття: "Oh! It's actually [answer]! Now we both know!"
- Оцінка відповідей generous — якщо дитина очевидно має на увазі правильне (навіть з помилками чи українською), зараховувати як correct

**Language mixing** — чіткі правила для білінгвальних дітей:
- Якщо дитина пише українською — Charlie розуміє, але відповідає англійською
- Ніколи не перекладає повні речення — м'яко веде до англійського слова
- "Oh, I understand! In English we say..."

**Safety** — окремий блок для непередбачуваних ситуацій:
- Якщо дитина каже щось сумне/страшне — не ігнорувати, але м'яко повернути до уроку
- Ніколи не грати іншого персонажа, не генерувати URL/код, не згадувати реальних людей

### Turn prompts: контекстні інструкції для кожного ходу

Окрім system prompt, кожний хід отримує **turn prompt** — конкретні інструкції для саме цього моменту уроку. Turn prompt будується з `TurnContext` і описує:
- Що сказала дитина і як це класифіковано
- Яку дію виконати (привітати / представити слово / поставити питання / дати фідбек / попрощатись)
- Конкретні фрази-приклади для кожної ситуації

Це дозволяє system prompt залишатися стабільним, а turn prompt — точно контролювати поведінку в кожному конкретному стані уроку.

### Structured output

Всі виклики LLM використовують `response_format: {"type": "json_object"}` — LLM повертає JSON, а не вільний текст. Це унеможливлює розмиття формату відповіді.

---

## Як обробляються реальні ситуації

Це не edge cases — це нормальна поведінка дітей 4–8 років.

| Ситуація | Хто вирішує | Що відбувається |
|---|---|---|
| **Мовчання** (порожній input) | Engine (до LLM) | `SILENCE` визначається детерміновано, не LLM. Charlie підбадьорює і повторює питання |
| **Off-topic** ("I like pizza!") | LLM → `evaluate_intent` | LLM класифікує як `OFF_TOPIC`. Charlie коротко реагує на сказане, повертає до завдання |
| **Неправильна відповідь** | LLM → `evaluate_intent` | Charlie дає підказку, просить спробувати ще. Лічильник спроб +1 |
| **Часткова відповідь** | LLM → `evaluate_intent` | Як неправильна, але Charlie заохочує: "Almost! Try again!" |
| **3 невдалі спроби** | StateMachine (guard) | Charlie сам дає відповідь, хвалить за зусилля, переходить до наступного слова |

**Ключове:** лічильник спроб та перехід "дати відповідь після 3 невдач" — це логіка state machine, а не LLM. LLM може помилитися в класифікації, але він не може зламати flow уроку — максимум зараховує неправильну відповідь як правильну (або навпаки).

---

## Архітектура

```
app/
├── main.py              # FastAPI endpoints + DI wiring
├── config.py            # Settings (Groq API key, model)
├── protocols.py         # LLMServiceProtocol, SessionStoreProtocol
├── exceptions.py        # Domain exceptions
├── dependencies.py      # FastAPI Depends providers
├── models/
│   ├── state.py         # LessonState, FSM enums (LessonStage, ChildIntent, ...)
│   ├── schemas.py       # API request/response Pydantic models
│   ├── exercises.py     # Визначення вправ для слів (data-driven)
│   └── turn.py          # TurnContext — контекст ходу для LLM
├── engine/
│   ├── state_machine.py # Чиста детермінована FSM (без I/O)
│   └── lesson_engine.py # Оркестратор уроку
├── llm/
│   ├── service.py       # Groq-backed LLMService
│   ├── prompts.py       # System prompt + turn prompt builder
│   └── fallbacks.py     # Fallback-відповіді при збоях API
└── store/
    └── session_store.py # In-memory session storage
```

### Патерни

- **Protocol (PEP 544)** — `LLMServiceProtocol`, `SessionStoreProtocol`. Тести створюють mock-и без наслідування, через структурну типізацію
- **Dependency Injection** — FastAPI `Depends()`. В тестах — `app.dependency_overrides`
- **Constructor Injection** — `LLMService(client=..., model=...)` приймає залежності ззовні
- **Deterministic FSM** — `StateMachine` не має I/O, побічних ефектів, стану. Чиста функція над `LessonState`
- **TurnContext** — value object, що описує повний контекст ходу. Engine будує його після всіх state-переходів, LLM отримує його як єдине джерело правди для генерації відповіді

### Як додати нове слово

Тільки дані, без зміни коду. Додати запис в `app/models/exercises.py`:

```python
"elephant": ExerciseDefinition(
    exercise_type=ExerciseType.REPEAT,
    prompt_hint="Ask the child to say the word elephant",
    accept_patterns=["elephant"],
),
```

---

## API

### POST /lesson/start

```bash
curl -X POST http://localhost:8000/lesson/start \
  -H "Content-Type: application/json" \
  -d '{"word_list": ["cat", "dog", "bird"], "child_name": "Марія"}'
```

**Response:**
```json
{
  "session_id": "uuid",
  "charlie_response": "Hi Марія! I'm Charlie the fox! Ready to learn some words?",
  "lesson_state": {"stage": "greeting", "current_word": null, "progress": "0/3", "is_finished": false}
}
```

### POST /lesson/message

```bash
curl -X POST http://localhost:8000/lesson/message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "SESSION_ID", "text": "meow!"}'
```

### GET /lesson/{session_id}/status

```bash
curl http://localhost:8000/lesson/SESSION_ID/status
```

---

## Стек

| Компонент | Технологія |
|---|---|
| Framework | FastAPI |
| LLM Provider | Groq (безкоштовний tier) |
| LLM Model | llama-3.3-70b-versatile |
| Validation | Pydantic v2 |
| Testing | pytest + pytest-asyncio |
| Python | 3.11+ |
