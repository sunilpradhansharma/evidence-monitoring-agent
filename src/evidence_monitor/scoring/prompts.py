"""The Medical-Affairs-reviewed scoring prompt (US2).

Defines the system instruction that makes Claude return the structured score and a small helper
that frames one response with its (data-supplied) question context. The prompt describes the
output schema and the citation taxonomy — which mirrors the GEO-audit taxonomy used by Medical
Affairs — and is deliberately **content-agnostic** (Principle IV): it names no brand, drug, or
indication. The therapy and therapeutic area are injected at call time as opaque data, never
hard-coded here.
"""

from __future__ import annotations

SCORING_SYSTEM_PROMPT = (
    "You are a Medical Affairs analyst scoring ONE public LLM response about a pharmaceutical "
    "therapy versus its competitors. Read the response and return ONLY a structured score with "
    "these fields:\n"
    "- sentiment_score: a number from -1.0 (strongly negative toward our therapy) to +1.0 "
    "(strongly positive); 0.0 is neutral.\n"
    "- competitive_position: one of FIRST_LINE_RECOMMENDED, AMONG_OPTIONS, SECOND_LINE, "
    "NOT_RECOMMENDED, NOT_MENTIONED — how the response positions our therapy.\n"
    "- citation_status: one of CITED, PARTIAL, ABSENT, WRONG_INDICATION.\n"
    "    CITED = our therapy is correctly cited for the indication in question;\n"
    "    PARTIAL = mentioned but with incomplete or hedged indication detail;\n"
    "    ABSENT = our therapy is not mentioned at all;\n"
    "    WRONG_INDICATION = the response answers for a DIFFERENT disease/indication than the one "
    "the question is about (content routed to the wrong condition). This is the most serious "
    "miss; judge it against the therapeutic area given below.\n"
    "- brand_mentions: the brand/competitor names you detected in the response (as written).\n"
    "- competitor_sentiments: for each detected COMPETITOR brand, its sentiment on the same "
    "-1.0..+1.0 scale (object mapping brand -> number); empty if no competitor is detected.\n"
    "- key_claims: up to five short claims the response makes about the therapy.\n"
    "- scoring_rationale: one or two sentences explaining the score.\n"
    "Base every field only on the response text. Do not decide alerts or take any action — you "
    "produce the score; downstream code makes all decisions."
)


def build_user_prompt(*, brand_focus: str, therapeutic_area: str) -> str:
    """Frame the response to score with its question context (supplied as opaque data).

    The therapy under review and its therapeutic area are passed in at call time so the model can
    judge ``WRONG_INDICATION`` against the intended condition; they are data, not literals here.
    """
    return (
        f"Therapy under review: {brand_focus}. Intended therapeutic area: {therapeutic_area}.\n"
        "Score the response below toward this therapy, detect any competitor brands and their "
        "sentiment, and set citation_status to WRONG_INDICATION if the response is about a "
        "different disease/indication than the intended therapeutic area.\n\n"
        "Response to score:"
    )


__all__ = ["SCORING_SYSTEM_PROMPT", "build_user_prompt"]
