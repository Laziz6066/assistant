# Multi-turn Dialog — Design Spec

**Date:** 2026-05-20
**Status:** Approved, ready for implementation plan
**Sub-project:** Beta (post-MVP, post-Piper-TTS, post-ollama, post-wake-word, post-tray)
**Depends on:** voice-assistant branch at commit `596dfb8` or later

## 1. Goal

Add multi-turn slot inheritance via pronoun resolution: when the user says *"закрой его"* right after *"открой telegram"*, the assistant rewrites the transcript to *"закрой telegram"* before NLU, producing `close_app(app="telegram")`. No ollama dependency.

## 2. Scope

**In:**
- `ContextStore`: bounded LRU of recent intents with TTL expiration
- `ContextualRouter(NLURouter)`: wraps an inner router; rewrites Russian/English pronouns to the last entity when context is fresh
- Pipeline integration: writes successful intents into the store
- `DialogConfig.enabled`/`context_ttl_s`/`context_size` in `config.py`, `enabled: true` by default
- Pronoun list (one-time, frozen for v1): `его, её/ее, их, это, этот/эту, этого/этому, тот/та/то, того/тому, ту`; English: `it, this, that`
- Slot-source priority: `app` > `name` > `query` > `url`
- Skip-list (never stored as context): `Intent.unknown()`, `confirm_yes`, intents with no slots

**Out (deferred):**
- LLM-enriched dialog history (passing prior turns into ollama prompt) — separate Beta feature
- Long-term memory across sessions
- Complex coreference (multiple competing entities in one turn)
- Verb-aware rewriting (e.g., *"и не закрывай его" → confirm-yes-no* — out of scope)
- Confirmation flows tied to context ("сделай это" prompting "что именно?")
- Localizable pronoun set via config

## 3. Decisions

| Question | Decision |
|---|---|
| Resolution strategy | Rules-only (regex pronoun replacement using last entity from `ContextStore`) |
| Library | Pure stdlib (`re`, `collections.deque`, `threading`); no new dependencies |
| Context TTL | 60 s default (configurable via `dialog.context_ttl_s`) |
| Context size | 5 intents (configurable via `dialog.context_size`) |
| Default `enabled` | `true` (no external resources required, broad UX win) |
| Failure policy | Any resolution failure → pass-through original transcript → existing pipeline handles unknown |
| Entity slot priority | `app` > `name` > `query` > `url` (first match wins) |
| `confirm_yes` handling | Never stored as context source — it's a meta-command |
| Cross-thread safety | `ContextStore` uses a `threading.Lock` for `add`/`get_recent_entity`/`clear` |

## 4. Architecture

### 4.1 New files

```
src/voice_assistant/nlu/
  context_store.py    # ContextStore (deque + TTL + Lock)
  contextual.py       # ContextualRouter(NLURouter) wrapping inner router
```

### 4.2 Modified files

```
src/voice_assistant/config.py
  + class DialogConfig(BaseModel):
        enabled: bool = True
        context_ttl_s: float = 60.0
        context_size: int = 5
  + AppConfig.dialog: DialogConfig

src/voice_assistant/main.py
  - Pipeline.__init__ gains optional `context_store: ContextStore | None`
  - Pipeline.process_segment writes successful intents to the store
  - _build: construct ContextStore + wrap NLU chain in ContextualRouter
    when cfg.dialog.enabled

config/default.yaml
  + dialog: ...

README.md
  + Dialog section + manual checklist additions
```

No new dependencies. No changes to MVP execution path when `dialog.enabled: false`.

### 4.3 Data flow

```
worker thread:
  segment ─→ Pipeline.process_segment
                 │
                 ▼
              asr.transcribe(segment) ─→ Transcript
                 │
                 ▼
              nlu.route(transcript)
                 │ (nlu = ContextualRouter(inner=RulesRouter or LLMFallbackRouter))
                 ▼
              ContextualRouter.route(transcript):
                 entity = store.get_recent_entity()
                 if entity and pronoun_re.search(text):
                     text' = pronoun_re.sub(entity, text)
                     return inner.route(Transcript(text', ...))
                 return inner.route(transcript)
                 │
                 ▼
              registry.dispatch(intent, ctx) ─→ ExecutionResult
                 │
                 ▼
              if result.success and store is not None:
                  store.add(intent)
                 │
                 ▼
              feedback.emit(...)
```

### 4.4 `ContextStore` interface

```python
class ContextStore:
    """Bounded LRU of recently dispatched intents with TTL expiration.

    Thread-safe (one Lock guards all mutations and reads).
    """

    def __init__(self, max_size: int = 5, ttl_s: float = 60.0,
                 clock: Callable[[], float] | None = None) -> None:
        # clock injectable for tests; defaults to time.monotonic
        ...

    def add(self, intent: Intent) -> None:
        """Append intent to the deque if it has slots and isn't unknown/confirm_yes.
        Silently ignores ineligible intents."""

    def get_recent_entity(self) -> tuple[str, str] | None:
        """Return (entity_value, slot_name) from the most-recent intent that
        passes filters (eligible + within TTL), preferring slot priority.
        Returns None if nothing eligible."""

    def clear(self) -> None:
        """Drop all stored intents. Used by tests; also called on SIGINT
        if we ever want a fresh start, but main() doesn't currently call it."""
```

Internal state: `deque[tuple[Intent, float]]` where float is monotonic timestamp at insertion.

### 4.5 `ContextualRouter` interface

```python
class ContextualRouter(NLURouter):
    """NLURouter that rewrites pronouns in the transcript before delegating
    to an inner router.
    """

    def __init__(self, inner: NLURouter,
                 store: ContextStore | None) -> None:
        self._inner = inner
        self._store = store

    def route(self, transcript: Transcript) -> Intent:
        # 1. If store is None or empty → passthrough
        # 2. Find pronouns in transcript.text
        # 3. If pronouns present AND store has a recent entity:
        #      rewrite text by replacing all pronouns with entity value
        #      log DEBUG of the rewrite
        #      call inner.route on a Transcript copy with rewritten text
        # 4. Else: passthrough to inner.route(transcript)
```

The replacement is greedy: every pronoun match is replaced with the same entity. We don't try to distinguish "его" vs "её" by gender — the rules router will fail on mismatches and we degrade to `Intent.unknown()` naturally.

### 4.6 Pipeline changes

`Pipeline.__init__` gains `context_store: ContextStore | None = None`. Default `None` keeps backward compatibility for any test that constructs `Pipeline` directly.

In `process_segment`, after `result = self.registry.dispatch(intent, self.ctx)`:

```python
if result.success and self.context_store is not None:
    self.context_store.add(intent)
```

`ContextStore.add` already filters ineligible intents internally, so the only check at the call site is `result.success` (don't store failed dispatches as context).

## 5. Resolution Algorithm

### 5.1 Pronoun set

```python
_PRONOUNS = {
    "его", "её", "ее", "их",
    "это", "этот", "эту", "этого", "этому",
    "тот", "та", "то", "того", "тому", "ту",
    "it", "this", "that",
}

_PRONOUN_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in _PRONOUNS) + r")\b",
    flags=re.IGNORECASE,
)
```

`\b` word-boundary anchors prevent `"эту"` from matching inside `"этузиазм"`.

### 5.2 Entity slot priority

```python
_ENTITY_SLOT_PRIORITY = ("app", "name", "query", "url")
```

`get_recent_entity()` iterates `deque` from newest to oldest:

```python
def get_recent_entity(self) -> tuple[str, str] | None:
    now = self._clock()
    with self._lock:
        for intent, ts in reversed(self._buf):  # newest first
            if now - ts > self._ttl_s:
                break  # everything older is also expired (deque ordered)
            for slot_name in _ENTITY_SLOT_PRIORITY:
                if slot_name in intent.slots:
                    val = intent.slots[slot_name]
                    if isinstance(val, str) and val.strip():
                        return (val.strip(), slot_name)
    return None
```

### 5.3 Rewrite

```python
def _rewrite(self, text: str) -> str:
    entity = self._store.get_recent_entity() if self._store else None
    if entity is None:
        return text
    if not _PRONOUN_RE.search(text):
        return text
    value, _slot_name = entity
    return _PRONOUN_RE.sub(value, text)
```

### 5.4 Worked examples

| Last intent | Transcript | After rewrite | Final |
|---|---|---|---|
| `open_app(app="telegram")` | "закрой его" | "закрой telegram" | `close_app(app="telegram")` |
| `open_app(app="telegram")` | "сверни его" | "сверни telegram" | `Intent.unknown()` (no `sverni {app}` rule) — acceptable |
| `web_search(query="weather")` | "повтори это" | "повтори weather" | `Intent.unknown()` (no such intent) |
| `minimize_all` (slotless) | "закрой его" | "закрой его" | `Intent.unknown()` (no entity) |
| (no recent context) | "закрой его" | "закрой его" | `Intent.unknown()` |
| `confirm_yes` then `open_app(app="telegram")` | "закрой его" | "закрой telegram" | OK (confirm_yes was skipped) |

### 5.5 Multiple pronouns

If a transcript has two pronouns ("открой его и сверни это"), both get the SAME entity. Rationale: rules-NLU can't model two distinct anaphors, and trying to be clever here adds bugs.

## 6. Configuration

```yaml
# config/default.yaml
dialog:
  enabled: true
  context_ttl_s: 60.0
  context_size: 5
```

`enabled: false` → `_build` doesn't construct `ContextStore` or wrap NLU in `ContextualRouter`. Pipeline gets `context_store=None`.

## 7. Error Handling

| Layer | Error | Behaviour |
|---|---|---|
| `ContextStore.add` | Intent.unknown / confirm_yes / no slots | Silently ignored — not stored |
| `ContextStore.add` | Concurrent call from multiple threads | Lock serializes |
| `ContextStore.get_recent_entity` | Empty store | Returns `None` |
| `ContextStore.get_recent_entity` | All entries expired | Returns `None` (iteration breaks on first expired since deque is time-ordered) |
| `ContextualRouter.__init__` | `store=None` | OK — degrades to pure passthrough |
| `ContextualRouter.route` | Inner router raises | Propagates (matches current behaviour of Composite/Fallback chains) |
| `Pipeline` with `context_store=None` | Successful intent dispatch | Skip the `.add()` call; no exception |
| Pronoun regex crash | (impossible; static pattern) | N/A |

**Invariant:** Whatever happens at the dialog layer, the user gets the same response they'd have gotten without `dialog.enabled` — either a successful intent OR the existing "Не понял, повтори".

## 8. Testing Strategy

### 8.1 Mocks

- `time.monotonic` injectable via `ContextStore(clock=...)` for TTL tests; otherwise real
- Inner `NLURouter` mocked as `MagicMock(spec=NLURouter)` in `ContextualRouter` tests
- No external dependencies to mock

### 8.2 Unit tests

`tests/unit/nlu/test_context_store.py` (~8):

```python
def test_add_stores_eligible_intent()
def test_add_skips_unknown()
def test_add_skips_confirm_yes()
def test_add_skips_slotless()
def test_get_recent_entity_returns_newest()
def test_get_recent_entity_returns_none_when_empty()
def test_get_recent_entity_respects_ttl()  # uses injected clock
def test_get_recent_entity_respects_slot_priority()  # app > name > query > url
def test_deque_evicts_oldest_at_max_size()
def test_clear_empties_store()
```

`tests/unit/nlu/test_contextual.py` (~10):

```python
def test_passthrough_when_no_pronouns()
def test_passthrough_when_store_empty()
def test_passthrough_when_store_none()
def test_rewrite_replaces_simple_pronoun()
def test_rewrite_replaces_multiple_pronouns_with_same_entity()
def test_each_russian_pronoun_recognized()  # parametrize
def test_each_english_pronoun_recognized()  # parametrize
def test_case_insensitive_match()
def test_word_boundary_prevents_partial_match()
def test_expired_context_treated_as_empty()
def test_inner_router_called_with_rewritten_transcript()
def test_inner_router_exception_propagates()
```

`tests/unit/test_main.py` extend (~3):

```python
def test_build_wraps_in_contextual_router_when_dialog_enabled()
def test_build_skips_contextual_router_when_dialog_disabled()
def test_pipeline_constructor_accepts_context_store()
def test_pipeline_writes_successful_intent_to_context_store()
def test_pipeline_does_not_write_failed_dispatch_to_store()
```

`tests/unit/test_config.py` extend (~3):

```python
def test_dialog_config_default_values()
def test_dialog_config_accepts_overrides()
def test_app_config_has_dialog_section()
```

### 8.3 Integration test

`tests/integration/test_dialog.py` (1):

```python
def test_two_turn_open_then_close(tmp_path):
    """Real RulesRouter + ContextStore + ContextualRouter wired together.
    Turn 1: 'открой телега' → open_app{app=telegram}
    Turn 2: 'закрой его' → close_app{app=telegram}
    """
```

### 8.4 What we don't test

- Performance of pronoun regex over long transcripts (1-line transcripts are realistic)
- Bilingual mixing within a single utterance ("закрой this telegram") — defer
- Race against the Pipeline worker reading the store mid-add (Lock guarantees safety; not worth a stress test)

## 9. README addition

```markdown
## Multi-turn dialog (slot inheritance)

После выполнения команды с слотом ассистент короткое время (60 с по умолчанию) помнит её аргумент и понимает местоимения:

```
открой telegram     → запускает Telegram
закрой его          → закрывает Telegram (наследуется app=telegram)
```

Работает для русских и английских местоимений: `его, её, их, это, этот, эту, того, тому, ту, it, this, that`. Состояние очищается через `dialog.context_ttl_s` секунд.

Отключить: `dialog.enabled: false` в `config/default.yaml`. Контекст хранится только в памяти — после рестарта пустой.
```

## 10. Manual Verification Checklist

Append to `README.md`:

- [ ] "открой блокнот" → "закрой его" → блокнот закрывается
- [ ] Пауза 70 секунд между turns → второй turn даёт "Не понял, повтори"
- [ ] "сверни всё" (slotless) → "закрой его" → "Не понял" (нет entity)
- [ ] `dialog.enabled: false` → "открой блокнот" → "закрой его" → "Не понял"
- [ ] "открой telegram" → "открой это" → пытается открыть telegram повторно (приемлемо)
- [ ] Несколько turns подряд: `open_app(telegram)` → `open_app(chrome)` → "закрой его" → закрывает Chrome (последнее entity)
- [ ] `confirm_yes` после команды НЕ затирает context: "выключи компьютер" → confirm → "верни его" не пытается унаследовать "yes"

## 11. Open Questions / Future Work

- **LLM-enriched dialog** — pass last N turns into `LLMFallbackRouter` system prompt for free-form anaphora resolution. Already designed in ollama spec §12.
- **Verb-aware rewriting** — *"и не открывай его"* должно стать `negate(open_app{app=X})`. Out of v1 scope (no negation in intent vocabulary).
- **Cross-session memory** — persist `ContextStore` to disk so restart preserves context. Useful for long-running daemons; trivial to add later.
- **Multiple competing entities** — *"открой блокнот и chrome, закрой его"* — what's "его"? Today: most-recent wins (chrome). Future: ambiguity → ask user.
- **Inverse operations** — *"открой telegram"* → *"верни как было"* should close it. Requires intent inverse table. Defer.
- **TTS-suppression after context-based command** — currently no special handling; the TTS reply uses the same path. Fine.

## 12. References

- MVP design spec: `docs/superpowers/specs/2026-05-19-voice-assistant-design.md`
- ollama LLM fallback (which explicitly defers this feature): `docs/superpowers/specs/2026-05-20-ollama-fallback-design.md` §12
- Wake-word spec (sibling Beta feature pattern): `docs/superpowers/specs/2026-05-20-wake-word-design.md`
