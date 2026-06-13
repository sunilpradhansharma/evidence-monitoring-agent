# Contract — LLM Adapter Protocol

`llm/adapters/base.py`. Every monitored target implements this protocol. Adding a target = a new
adapter + a `config/targets.yaml` entry, with **no change to orchestration** (Principle V/X).

## Protocol

```
class LLMAdapter(Protocol):
    target_id: str
    name: str

    def submit(self, *, question_text: str, persona: Persona, system_prompt: str,
               params: TargetParams) -> AdapterResult: ...

    def health(self) -> HealthResult: ...   # reachability + credential check
```

## `AdapterResult`
| Field | Type | Notes |
|-------|------|-------|
| status | ResponseStatus | SUCCESS / FAILED / TRUNCATED / BLOCKED |
| response_text | str | full, unedited (empty allowed) |
| response_tokens | int | |
| finish_reason | FinishReason | STOP / LENGTH / ERROR / SAFETY |
| model_version | str | resolved from config at call time |
| block_reason | str? | populated when BLOCKED (Gemini safety) |
| attempts | int | how many tries were made |

## Behavioral requirements (all adapters)

1. **Model id & params from config** — never hard-coded (Principle V).
2. **Retry/backoff** — retry transient failures (timeout, 429, 5xx) up to the configured budget
   with exponential backoff (default 2s/4s/8s). After exhaustion → `FAILED` (no exception escapes).
3. **Rate limiting** — honor per-target `rpm_limit`/`tpm_limit`.
4. **Status mapping** — length cap → `TRUNCATED`; safety/filter block → `BLOCKED` (distinct from
   `FAILED`, esp. Gemini); empty success → `SUCCESS` with empty text.
5. **OFFLINE/MOCK mode** — when enabled, return deterministic canned `AdapterResult`s with **no
   network call** (Principle XI); identical inputs → identical outputs.
6. **No secrets in errors/logs** — surface non-secret messages only (Principle: secrets never logged).

## Per-adapter notes
- `openai_gpt4o.py` — Chat Completions; messages array (system + single user); pinned model version.
- `gemini.py` — system instruction + user part; map safety blocks → `BLOCKED` with reason.
- `claude_target.py` — Claude **as an end-user** (non-orchestrator system prompt); role tagged TARGET.
- `open_evidence.py` — **conditional**; only invoked for PROVIDER-persona questions and only when
  enabled in config; absent target does not count against the capture rate.
