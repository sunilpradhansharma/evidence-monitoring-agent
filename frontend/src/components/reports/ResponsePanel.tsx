import { useEffect, useState } from "react";
import { getResponse, type ResponseDetail } from "../../api";
import {
  isProviderEvidenceDev,
  PROVIDER_EVIDENCE_DEV_NOTE,
  targetLabel,
} from "../../targets";

export default function ResponsePanel({
  responseId,
  onClose,
}: {
  responseId: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<ResponseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setData(null);
    setError(null);
    getResponse(responseId)
      .then((d) => active && setData(d))
      .catch((e) => active && setError(String(e)));
    return () => {
      active = false;
    };
  }, [responseId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Response detail">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} aria-hidden="true" />
      <div className="relative z-10 flex h-full w-full max-w-xl flex-col overflow-y-auto bg-surface shadow-lift">
        <div className="flex items-center justify-between border-b border-hair px-5 py-3">
          <h3 className="font-bold">Response detail</h3>
          <button className="btn px-3 py-1" onClick={onClose} aria-label="Close panel">
            Close
          </button>
        </div>
        <div className="space-y-4 px-5 py-4 text-sm">
          {error && <p className="text-neg-ink">Could not load response: {error}</p>}
          {!data && !error && <p className="text-ink-soft">Loading…</p>}
          {data && (
            <>
              <div className="flex flex-wrap gap-2">
                <span className="id tag tag-muted">{data.question_id}</span>
                <span className="tag tag-muted">{targetLabel(data.llm_name)}</span>
                <span className="tag tag-muted">{data.persona.toLowerCase()}</span>
                <span className="tag">{data.status.toLowerCase()}</span>
              </div>
              {isProviderEvidenceDev(data.llm_name) && (
                <div className="rounded-lg border border-brand-line bg-brand-soft p-3 text-xs leading-relaxed text-ink">
                  <span className="font-bold text-brand-dark">How this was produced — </span>
                  {PROVIDER_EVIDENCE_DEV_NOTE}
                </div>
              )}
              {data.score && (
                <div className="rounded-lg border border-hair bg-surface-muted p-3">
                  <p className="font-semibold">Scoring rationale</p>
                  <p className="mt-1 text-ink-soft">{data.score.scoring_rationale}</p>
                  <p className="mt-2 text-xs text-ink-soft">
                    sentiment {data.score.sentiment_score.toFixed(2)} ·{" "}
                    {data.score.competitive_position.toLowerCase().replace(/_/g, " ")} ·{" "}
                    {data.score.citation_status.toLowerCase().replace(/_/g, " ")}
                  </p>
                  {data.score.brand_mentions.length > 0 && (
                    <p className="mt-1 text-xs text-ink-soft">
                      brands: {data.score.brand_mentions.join(", ")}
                    </p>
                  )}
                </div>
              )}
              <div>
                <p className="font-semibold">Full response text</p>
                <p className="mt-1 whitespace-pre-wrap text-ink">{data.response_text || "—"}</p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
