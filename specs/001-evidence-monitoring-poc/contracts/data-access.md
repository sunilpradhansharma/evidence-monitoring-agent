# Contract — Data Access Protocol

`data_access/interface.py`. The production seam (Principle X). Core modules depend ONLY on these
protocols; the SQLite implementation (`sqlite_store.py`) is swappable for Aurora/DynamoDB by config.

## Repository protocols

```
class QuestionRepository(Protocol):
    def upsert(self, q: Question) -> Question: ...          # new version on edit; never hard-delete
    def set_approval(self, question_id: str, status: ApprovalStatus, approver: str,
                     reason: str | None = None) -> Question: ...
    def list(self, *, approval_status=None, active=None, persona=None,
             therapeutic_area=None) -> list[Question]: ...
    def approved_active(self) -> list[Question]: ...        # the run-eligible set

class ResponseRepository(Protocol):
    def insert(self, r: Response) -> Response: ...          # IMMUTABLE: raises on any update attempt
    def get(self, response_id: str) -> Response | None: ...

class ScoringRepository(Protocol):
    def add_version(self, s: ScoringRecord) -> ScoringRecord: ...   # links response_id; never mutates response
    def latest_for(self, response_id: str) -> ScoringRecord | None: ...
    def versions_for(self, response_id: str) -> list[ScoringRecord]: ...

class AlertRepository(Protocol):
    def insert(self, a: Alert) -> Alert: ...
    def list(self, *, order_by_severity=True) -> list[Alert]: ...

class RunRepository(Protocol):
    def create(self, trigger: TriggerType) -> Run: ...
    def checkpoint(self, run_id: str, last_completed_question_id: str) -> None: ...
    def finalize(self, run_id: str, totals: RunTotals) -> Run: ...

class AuditWriter(Protocol):                                # data_access/audit.py
    def append(self, event: AuditEvent) -> None: ...        # APPEND-ONLY; no update/delete
```

## Query contract (`queries.py`)

`query_responses(filters, page, page_size) -> Page[ResponseView]` supporting any combination of:
`llm, persona, therapeutic_area, brand, domain, date_from, date_to, sentiment_min, sentiment_max,
alert_status, status` (FR-012). Returns total count for pagination. Exports (CSV/JSON) consume the
same filter object.

## Guarantees enforced at this layer
- **Immutability** — `ResponseRepository.insert` is write-once; updates raise.
- **Versioning** — `ScoringRepository.add_version` and `QuestionRepository.upsert` retain history.
- **Append-only audit** — `AuditWriter` exposes no mutation.
- **Soft-delete / retention** — deletes mark inactive with reason + timestamp; ≥24-month retention.
- **No content literals** — repositories store brand/competitor/indication values as data only.
