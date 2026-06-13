# LLM Adapter Rules

These rules apply to all code in `src/evidence_monitor/llm/`. Each provider gets one adapter
under `adapters/`.

- **Base protocol** — every adapter implements the base adapter interface in
  `adapters/base.py`. Match its method signatures exactly; do not widen or fork the protocol.
- **Retry / backoff** — wrap remote calls with retry and exponential backoff on transient
  failures (timeouts, 429s, 5xx). Cap attempts; surface a clear error after the final retry.
- **Offline mock mode** — every adapter supports a mock mode that returns canned responses with
  **no network call**, for tests and `/capture-rate-eval`. Mock vs. live is selected by config,
  not by editing code.
- **Model id from config** — read model id, params, rate limits, and personas from
  `config/targets.yaml`. Never hard-code a model id, endpoint, or key in an adapter.
- **ToS** — before enabling a new provider target in production, confirm its Terms of Service
  permit this usage.
- **No orchestration changes from here** — adapters only translate requests/responses. Scoring
  decisions and alerting live in the orchestration layer, not in `llm/`.
- **Every adapter ships a unit test** exercised in mock mode (happy path + one retry path).
