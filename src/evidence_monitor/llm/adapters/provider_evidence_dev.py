"""Synthesized Evidence — a literature-synthesis monitored target (PubMed E-utilities + Claude).

This target is a first-class, Provider-persona literature-synthesis target: it synthesizes PUBLISHED
medical literature from public PubMed (E-utilities) using Claude. It is **NOT** Open Evidence and
uses NO Open Evidence data; its output is its own and must never be presented as, or attributed to,
Open Evidence. It is labelled **"Synthesized Evidence"** everywhere it appears (``kind: synthesis``
in config). The class/module keep their original ``provider_evidence_dev`` identifiers so stored
provenance (``llm_name``) and the adapter registry stay stable.

How it works (two steps, both behind this adapter and the existing retry/backoff seam):

1. Query public **PubMed E-utilities** (``esearch`` → ``efetch``) for the question text to retrieve
   a small set of recent, relevant abstracts. Basic access needs no key; NCBI asks callers to send
   ``tool`` + ``email`` (from config) and supports an optional ``api_key`` (config/env) for higher
   rate limits.
2. Pass those abstracts to the existing **Claude client** (orchestrator role) and ask it to
   synthesize a concise, citation-grounded answer **from the provided abstracts only** (the prompt
   states these are abstracts, not full text). The synthesized text — plus a provenance footer
   recording the PubMed query and the PMIDs used — becomes the captured response, scored through the
   normal pipeline.

Provenance is embedded in the immutable response text (a delimited "Sources" footer with the query
and PMIDs) so every synthesized answer is traceable to its sources without changing the data layer
or the Response schema (immutability preserved).

Constitution alignment: content-agnostic (the question / abstracts are opaque data; no drug,
competitor, or indication names appear here); model id + params from config; transient failures
retry and a hard failure marks the record FAILED so the run continues (the offline MOCK path returns
canned text with no network, like every other adapter).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from logging import Logger

from evidence_monitor.config.settings import Settings, get_settings
from evidence_monitor.data_access.models import LLMTarget
from evidence_monitor.llm.adapters.base import (
    _DEFAULT_MAX_ATTEMPTS,
    AdapterError,
    BaseAdapter,
    MockBehavior,
    TargetParams,
    TransientAdapterError,
    _Kind,
    _RawCompletion,
    _Request,
)
from evidence_monitor.llm.client import ClaudeClient

# Public NCBI E-utilities base (external network call — guarded behind this adapter).
_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Default number of abstracts to retrieve per question (kept small — NCBI usage policy + relevance).
_DEFAULT_RETMAX = 5

# The canonical display name. Structural/provider label (NOT a drug/competitor/indication name),
# shown wherever the target surfaces. It deliberately does NOT contain "Open Evidence". This mirrors
# the config ``display_name`` for this target (kept in sync; config is the source for surfaced UI).
DISPLAY_NAME = "Synthesized Evidence"

# Provenance footer marker (makes clear this is literature synthesis, not Open Evidence's output).
_SOURCES_HEADER = (
    "—— Sources (Synthesized Evidence: PubMed E-utilities + Claude synthesis; NOT Open Evidence) ——"
)

# Synthesis prompt: abstracts-only, cite PMIDs inline, no outside knowledge. Content-agnostic.
_SYNTH_SYSTEM = (
    "You are a clinical evidence assistant. Using ONLY the PubMed abstracts provided below "
    "(these are ABSTRACTS, not full text), write a concise, citation-grounded answer to the "
    "question. Cite each supporting source inline as [PMID:<id>]. If the abstracts do not address "
    "the question, say so plainly. Do not use outside knowledge and do not invent citations."
)

# A callable that performs one GET and returns (status_code, text). Injectable for tests so no
# live network is touched; the default uses httpx.
HttpGet = Callable[[str, dict], tuple[int, str]]


def _synthesis_instruction(question: str, abstracts: str) -> str:
    return (
        f"Question:\n{question}\n\n"
        f"PubMed abstracts (these are abstracts, not full text):\n{abstracts}\n\n"
        "Write the citation-grounded answer now."
    )


class ProviderEvidenceDevAdapter(BaseAdapter):
    """Dev stand-in Provider target: PubMed retrieval + Claude synthesis. NOT Open Evidence."""

    DISPLAY_NAME = DISPLAY_NAME

    def __init__(
        self,
        target: LLMTarget,
        *,
        mock: bool = False,
        mock_behavior: MockBehavior = MockBehavior.SUCCESS,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        # Injected for tests (no live network / no real Claude call); resolved live otherwise.
        claude: ClaudeClient | None = None,
        http_get: HttpGet | None = None,
        settings: Settings | None = None,
        retmax: int = _DEFAULT_RETMAX,
        logger: Logger | None = None,
    ) -> None:
        super().__init__(
            target,
            mock=mock,
            mock_behavior=mock_behavior,
            max_attempts=max_attempts,
            sleep=sleep,
            monotonic=monotonic,
        )
        self._claude = claude
        self._http_get = http_get
        self._settings = settings
        self._retmax = retmax
        self._logger = logger

    # --- the two-step live flow ------------------------------------------- #
    def _call_live(
        self, req: _Request, params: TargetParams, max_tokens: int, attempt: int
    ) -> _RawCompletion:
        settings = self._settings or get_settings()

        # Step 1 — PubMed esearch for relevant PMIDs.
        pmids = self._esearch(req.question_text, settings)
        if not pmids:
            body = (
                "No relevant PubMed abstracts were found for this question, so no "
                "evidence-grounded answer could be synthesized."
            )
            text = self._compose(body, req.question_text, [])
            return _RawCompletion(_Kind.STOP, text, tokens=max(1, len(body.split())))

        # Step 1b — fetch the abstracts for those PMIDs.
        abstracts = self._efetch(pmids, settings)

        # Step 2 — synthesize a cited answer FROM THE ABSTRACTS ONLY via the existing Claude client.
        claude = self._claude or ClaudeClient.from_settings(settings, logger=self._logger)
        completion = claude.orchestrate(
            _synthesis_instruction(req.question_text, abstracts),
            system=_SYNTH_SYSTEM,
            max_tokens=max_tokens,
        )
        body = completion.text.strip() or "(no synthesis returned)"
        tokens = completion.output_tokens or max(1, len(body.split()))
        return _RawCompletion(_Kind.STOP, self._compose(body, req.question_text, pmids), tokens)

    # --- PubMed E-utilities (guarded; retryable transient failures) ------- #
    def _get(self, endpoint: str, query: dict) -> str:
        url = f"{_EUTILS_BASE}/{endpoint}"
        if self._http_get is not None:
            status, text = self._http_get(url, query)
        else:  # pragma: no cover - live path only
            import httpx

            try:
                resp = httpx.get(url, params=query, timeout=20.0)
            except httpx.TransportError as exc:
                raise TransientAdapterError("pubmed transport error") from exc
            status, text = resp.status_code, resp.text
        if status == 429 or status >= 500:
            raise TransientAdapterError(f"pubmed transient: {status}")
        if status >= 400:
            raise AdapterError(f"pubmed error: {status}")
        return text

    def _id_params(self, settings: Settings) -> dict:
        """NCBI identification params from config (tool + email) plus an optional api_key."""
        params = {"tool": settings.ncbi_tool, "email": settings.ncbi_email}
        key = settings.ncbi_api_key
        if key is not None and key.get_secret_value().strip():
            params["api_key"] = key.get_secret_value()  # passed to NCBI; never logged
        return params

    def _esearch(self, term: str, settings: Settings) -> list[str]:
        query = {
            "db": "pubmed",
            "term": term,
            "retmax": str(self._retmax),
            "retmode": "json",
            **self._id_params(settings),
        }
        text = self._get("esearch.fcgi", query)
        try:
            data = json.loads(text)
            idlist = data["esearchresult"]["idlist"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AdapterError("pubmed esearch: unparseable response") from exc
        return [str(pmid) for pmid in idlist]

    def _efetch(self, pmids: list[str], settings: Settings) -> str:
        query = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "text",
            **self._id_params(settings),
        }
        return self._get("efetch.fcgi", query)

    # --- provenance footer (kept in the immutable response text) ---------- #
    def _compose(self, body: str, query: str, pmids: list[str]) -> str:
        lines = [
            body.strip(),
            "",
            _SOURCES_HEADER,
            f"PubMed query: {query}",
            "PMIDs: " + (", ".join(pmids) if pmids else "(none found)"),
        ]
        return "\n".join(lines)


__all__ = ["DISPLAY_NAME", "ProviderEvidenceDevAdapter"]
