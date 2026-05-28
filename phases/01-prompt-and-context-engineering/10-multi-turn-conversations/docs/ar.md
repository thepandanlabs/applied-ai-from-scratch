# المحادثات متعدّدة الأدوار والحالة (State)

> النموذج لا يتذكّر شيئًا. أنت تتذكّر كل شيء. كل محادثة هي بداية جديدة تُسلّم فيها النموذجَ سجلّه الخاص.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 01 (تشريح الطلب)، الدرس 04 (هندسة السياق context engineering)
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- شرح لماذا يكون Anthropic API عديم الحالة (stateless) وأين تعيش حالة المحادثة
- بناء فئة (class) باسم ConversationManager تحافظ على سجلّ الرسائل عبر الأدوار
- تنفيذ حفظ وتحميل الجلسة (session) باستخدام JSON
- التعامل مع حدود نافذة السياق (context window) عبر الاقتطاع (truncating) أو التلخيص
- تحديد أنماط فشل الإنتاج في الإدارة الساذجة للسجلّ

---

## المشكلة

أنت تبني روبوت محادثة (chatbot) لدعم العملاء. يسأل مستخدم سؤالًا، فتحصل على إجابة، ثم يتابع المستخدم: "هل يمكنك أن تشرح ذلك الجزء الأخير أكثر؟" فيردّ Claude: "ليس لديّ سياق عمّا تشير إليه."

نسي النموذج كل شيء من الدور السابق. يظنّ مستخدموك أن هناك خللًا.

لا يوجد خلل. الـ API عديم الحالة بحكم تصميمه. كل استدعاء لـ `client.messages.create()` مستقل. لا يملك النموذج وصولًا إلى الرسائل السابقة ما لم تُضمّنها صراحةً في الطلب. أما "الذاكرة" التي تختبرها في واجهات الويب فهي حالة من جانب العميل (client-side state) ترسلها الواجهة إلى النموذج في كل دور.

هذا ليس قيدًا يجب الالتفاف حوله. إنها خاصّية معمارية تمنحك تحكّمًا كاملًا فيما يراه النموذج من سياق ومتى. وبمجرد أن تستوعبها، يمكنك بناء محادثات بتحكّم دقيق: تلخيص السجلّات الطويلة، وحقن السياق بشكل انتقائي، وحفظ الجلسات عبر عمليات إعادة التشغيل، وتفريع المحادثات (forking)، وإعادة تشغيلها.

---

## المفهوم

### نموذج الـ API عديم الحالة

كل استدعاء للـ API مستقل. يحمل كل طلب سجلّ المحادثة الكامل الذي تريد أن يراه النموذج.

```
Turn 1                          Turn 2                          Turn 3
------                          ------                          ------

Client sends:                   Client sends:                   Client sends:
  system: "You are..."            system: "You are..."            system: "You are..."
  messages: [                     messages: [                     messages: [
    {user: "What is RAG?"}          {user: "What is RAG?"}          {user: "What is RAG?"}
  ]                                 {asst: "RAG is..."}             {asst: "RAG is..."}
                                    {user: "Give an example"}        {user: "Give an example"}
Model sees:                       ]                                 {asst: "Sure, imagine..."}
  1 message                                                          {user: "How do I build it?"}
                                Model sees:                        ]
                                  2 messages
                                                                Model sees:
                                                                  4 messages

The API has zero knowledge of Turn 1 when processing Turn 2.
YOU assembled that history and sent it.
```

### ما الحالة التي تتحمّل مسؤوليتها

```
┌────────────────────────────────────────────────────────────────────┐
│  YOUR APPLICATION (client-side state)                              │
│                                                                    │
│  - Message history: the list of user + assistant turns             │
│  - System prompt: role, constraints, output format                 │
│  - Session identity: which conversation is this?                   │
│  - Persistence: save to disk / database between restarts           │
│  - Truncation: what to do when history exceeds context window      │
│                                                                    │
└──────────────────────────────┬─────────────────────────────────────┘
                               |
                       Each API call:
                       system + messages[]
                               |
                               v
┌────────────────────────────────────────────────────────────────────┐
│  ANTHROPIC API (stateless)                                         │
│                                                                    │
│  - Processes what you send, exactly                                │
│  - Returns one assistant message                                   │
│  - Remembers nothing after the response                            │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### بنية الرسالة

يستخدم Anthropic API صيغة رسائل تناوبية بسيطة. يجب أن تتناوب الرسائل: مستخدم (user)، مساعد (assistant)، مستخدم، مساعد. ويجب أن تكون الرسالة الأولى من المستخدم.

```python
messages = [
    {"role": "user",      "content": "What is RAG?"},
    {"role": "assistant", "content": "RAG stands for Retrieval-Augmented Generation..."},
    {"role": "user",      "content": "Give me a concrete example."},
    {"role": "assistant", "content": "Sure. Imagine a customer support chatbot..."},
    {"role": "user",      "content": "How would I build that?"},
]
```

الـ system prompt مُعامِل (parameter) منفصل، وليس رسالة في القائمة.

### نافذة السياق والاقتطاع (Truncation)

لكل نموذج حدّ لنافذة السياق (بالـ tokens). يجب أن يتّسع السجلّ الكامل ضمن ذلك الحدّ. عندما يطول السجلّ أكثر من اللازم، أمامك ثلاثة خيارات:

```
Option 1: Sliding window         Option 2: Summarize old turns     Option 3: Hard limit
─────────────────────────        ─────────────────────────────     ──────────────
Keep only the last N turns.      Compress old turns into a          Refuse new input when
Oldest turns are dropped.        summary injected into system       context is full.
                                 prompt. Lossy but preserves        Simple. Bad UX.
Simple and fast.                 key context.
Loses long-range context.        Requires an extra LLM call.
```

في الإنتاج، الخيار 2 (التلخيص والضغط) عادةً ما يكون الأفضل للمحادثات الطويلة. والخيار 1 مناسب للجلسات القصيرة.

---

## البناء

### الخطوة 1: التثبيت والإعداد

```python
# pip install anthropic
# export ANTHROPIC_API_KEY=sk-ant-...
import os
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
import anthropic
```

### الخطوة 2: بنية بيانات الجلسة

```python
@dataclass
class Message:
    role: str    # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_api_format(self) -> dict:
        """Convert to the format Anthropic's API expects."""
        return {"role": self.role, "content": self.content}


@dataclass
class Session:
    session_id: str
    system_prompt: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    model: str = "claude-3-5-haiku-20241022"
    max_tokens: int = 1024

    def message_count(self) -> int:
        return len(self.messages)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "created_at": self.created_at,
            "messages": [asdict(m) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        messages = [Message(**m) for m in data.pop("messages", [])]
        session = cls(**data)
        session.messages = messages
        return session
```

### الخطوة 3: ConversationManager

```python
class ConversationManager:
    """
    Manages multi-turn conversations with the Anthropic API.

    Responsibilities:
    - Maintains message history per session
    - Assembles the full message list for each API call
    - Handles session save/load
    - Enforces a max turn limit (sliding window truncation)
    """

    def __init__(
        self,
        max_history_turns: int = 20,
        save_dir: Optional[str] = None,
    ):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.sessions: dict[str, Session] = {}
        self.max_history_turns = max_history_turns  # max user+assistant turn pairs
        self.save_dir = save_dir

    def create_session(
        self,
        session_id: str,
        system_prompt: str,
        model: str = "claude-3-5-haiku-20241022",
    ) -> Session:
        """Create a new conversation session."""
        session = Session(
            session_id=session_id,
            system_prompt=system_prompt,
            model=model,
        )
        self.sessions[session_id] = session
        return session

    def send_message(self, session_id: str, user_message: str) -> str:
        """
        Send a user message and get a response.

        Flow:
        1. Add user message to history
        2. Apply sliding window if history too long
        3. Build API request with full history
        4. Call API
        5. Add assistant response to history
        6. Return assistant response text
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' not found. Call create_session() first.")

        session = self.sessions[session_id]

        # Add user message to history
        session.messages.append(Message(role="user", content=user_message))

        # Apply sliding window: keep last N turn pairs (user + assistant = 1 pair)
        # We need to keep an even number of messages (pairs), then prepend any
        # leftover message so we always start with "user".
        max_messages = self.max_history_turns * 2
        if len(session.messages) > max_messages:
            # Drop oldest messages; ensure we start on a user message
            truncated = session.messages[-max_messages:]
            # If first message is assistant (truncation split a pair), drop it
            if truncated and truncated[0].role == "assistant":
                truncated = truncated[1:]
            session.messages = truncated

        # Build API message list (no timestamps, just role + content)
        api_messages = [m.to_api_format() for m in session.messages]

        # Call the API
        response = self.client.messages.create(
            model=session.model,
            max_tokens=session.max_tokens,
            system=session.system_prompt,
            messages=api_messages,
        )

        assistant_text = response.content[0].text

        # Add assistant response to history
        session.messages.append(Message(role="assistant", content=assistant_text))

        return assistant_text

    def get_history(self, session_id: str) -> list[Message]:
        """Return the full message history for a session."""
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' not found.")
        return self.sessions[session_id].messages

    def save_session(self, session_id: str, path: Optional[str] = None) -> str:
        """Save a session to JSON. Returns the file path used."""
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' not found.")

        if path is None:
            save_dir = self.save_dir or "/tmp"
            path = os.path.join(save_dir, f"session_{session_id}.json")

        session_data = self.sessions[session_id].to_dict()
        with open(path, "w") as f:
            json.dump(session_data, f, indent=2)
        return path

    def load_session(self, path: str) -> Session:
        """Load a session from JSON. Returns the loaded session."""
        with open(path) as f:
            data = json.load(f)
        session = Session.from_dict(data)
        self.sessions[session.session_id] = session
        return session
```

> **اختبار من الواقع:** يُكمل مستخدم محادثة دعم من 30 رسالة. تُحفظ الجلسة على القرص. وبعد ساعتين يعيد فتح المحادثة. عندما تُحمّل الجلسة ويسأل سؤالًا جديدًا، يجيب النموذج وكأنه يتذكّر كل شيء. كيف يعمل ذلك إذا كان الـ API عديم الحالة؟

### الخطوة 4: تشغيل محادثة تجريبية

```python
def run_demo():
    manager = ConversationManager(max_history_turns=10, save_dir="/tmp")

    # Create a session
    session = manager.create_session(
        session_id="demo-001",
        system_prompt=(
            "You are a concise Python tutor. "
            "Explain concepts clearly with short code examples. "
            "Remember what the student has already asked."
        ),
    )

    # Turn 1
    print("--- Turn 1 ---")
    reply = manager.send_message("demo-001", "What is a list comprehension?")
    print(f"Claude: {reply}\n")

    # Turn 2: follow-up depends on Turn 1
    print("--- Turn 2 ---")
    reply = manager.send_message("demo-001", "Can you show me a more complex example?")
    print(f"Claude: {reply}\n")

    # Turn 3: explicit reference to earlier turns
    print("--- Turn 3 ---")
    reply = manager.send_message("demo-001", "How does that compare to a regular for loop?")
    print(f"Claude: {reply}\n")

    # Save the session
    path = manager.save_session("demo-001")
    print(f"Session saved to: {path}")

    # Verify save/load round-trip
    manager2 = ConversationManager(max_history_turns=10)
    loaded = manager2.load_session(path)
    print(f"Session loaded: {loaded.message_count()} messages in history")

    # Continue the conversation after loading
    print("--- Turn 4 (after load) ---")
    reply = manager2.send_message("demo-001", "What is a generator expression and how is it different?")
    print(f"Claude: {reply}\n")

    return manager
```

---

## الاستخدام

لا يوفّر Anthropic SDK فئة ConversationManager جاهزة. أنت تدير قائمة الرسائل بنفسك. وإليك النهج الأدنى المعتمِد على الـ SDK مباشرةً:

```python
import anthropic

client = anthropic.Anthropic()
messages = []  # this is your conversation state

def chat(user_input: str) -> str:
    messages.append({"role": "user", "content": user_input})
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system="You are a helpful assistant.",
        messages=messages,
    )
    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})
    return reply

# Usage
print(chat("What is Python?"))
print(chat("What are its main use cases?"))
print(chat("How does it compare to JavaScript?"))
```

فئة ConversationManager التي بنيتَها في القسم السابق هي غلاف (wrapper) منظّم حول هذا النمط بالضبط. تضيف هويّة الجلسة، والحفظ/التحميل، وحدود السجلّ. أما الآلية الأساسية فمتطابقة: تحافظ على قائمة، تُلحق بها، وترسلها في كل استدعاء.

**الردود المتدفّقة (Streaming responses)** متطلّب إنتاجي شائع. يدعمها الـ SDK عبر مدير سياق (context manager):

```python
with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    system="You are a helpful assistant.",
    messages=messages,
) as stream:
    full_response = ""
    for text in stream.text_stream:
        print(text, end="", flush=True)
        full_response += text
    print()  # newline after streaming

# Append the full accumulated response to history
messages.append({"role": "assistant", "content": full_response})
```

التدفّق (streaming) لا يغيّر منطق إدارة السجلّ. ما زلت تجمّع الرد الكامل وتُلحقه بسجلّك قبل الدور التالي.

> **نقلة في المنظور:** يقول مدير منتج: "ألا يمكننا فقط تخزين المحادثة على الخادم وجعل الـ API يتذكّرها تلقائيًّا؟ لماذا علينا إرسال كل ذلك السجلّ في كل مرّة؟" كيف تشرح لماذا يُعدّ التصميم عديم الحالة في الواقع ميزة هندسية لأنظمة الإنتاج؟

---

## التسليم

الأصل (artifact) القابل لإعادة الاستخدام هو `outputs/skill-conversation-manager.md`. يوثّق نمط ConversationManager، واستراتيجيتَي النافذة المنزلقة (sliding window) والتلخيص، وأنماط فشل الإنتاج.

الكود القابل للتشغيل هو `code/main.py`. شغّله بـ:

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python main.py
```

تُشغّل التجربة محادثة من 4 أدوار، وتحفظ الجلسة في `/tmp/session_demo-001.json`، ثم تعيد تحميلها، وتُكمل المحادثة. افحص ملف JSON المحفوظ لترى سجلّ الرسائل الكامل.

---

## التقييم

تفشل المحادثات متعدّدة الأدوار بطرق لا تفشل بها الإكمالات أحادية الدور. يجب أن يغطّي تقييمك طبقة إدارة السجلّ، وليس مجرد الردود الفردية.

**ما الذي تقيسه:**

| نمط الفشل | كيف تكتشفه | كيف تمنعه |
|-------------|--------------|---------------|
| عدم تمرير السجلّ | يجيب النموذج وكأن الدور الأول لم يحدث | سجّل قائمة الرسائل الكاملة المُرسَلة في كل استدعاء API |
| الاقتطاع يُسقط سياقًا حرجًا | ينسى النموذج قيدًا ذُكر مبكرًا في المحادثة | اختبر محادثات تكون فيها المعلومة الحرجة في الدور 1 والسؤال في الدور 20 |
| انتهاك تناوب الأدوار | يُرجع الـ API خطأ 400 حول ترتيب الرسائل | تحقّق من تناوب الرسائل user/assistant قبل كل استدعاء API |
| تجاوز نافذة السياق | يُرجع الـ API خطأ 400 حول حدّ الـ tokens | عُدّ الـ tokens قبل الإرسال؛ واقتطع بشكل استباقي |
| تلف عند الحفظ/التحميل | تُنتج الجلسة المُحمّلة ردودًا خاطئة | اختبر الدورة الكاملة: احفظ، حمّل، أكمِل، تحقّق من إشارة النموذج إلى الأدوار السابقة |

**نمط اختبار التراجع:**

```python
def test_history_persistence(manager):
    """Verify the model references earlier turns after session load."""
    manager.create_session("test-01", system_prompt="Be concise.")
    manager.send_message("test-01", "My favorite color is blue.")
    manager.send_message("test-01", "My lucky number is 7.")
    path = manager.save_session("test-01")

    manager2 = ConversationManager()
    manager2.load_session(path)
    reply = manager2.send_message("test-01", "What did I tell you about myself?")

    assert "blue" in reply.lower() or "7" in reply.lower(), (
        f"Model failed to reference earlier turns. Reply: {reply}"
    )
```

يتحقّق نمط الاختبار هذا من سلسلة السجلّ من طرف إلى طرف، من الحفظ إلى التحميل إلى الاستدلال.
