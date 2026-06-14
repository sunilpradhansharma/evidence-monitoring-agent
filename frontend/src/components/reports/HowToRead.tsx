const DEFS: { term: string; def: string }[] = [
  {
    term: "Sentiment scale",
    def: "−1.0 (very negative about the therapy) to +1.0 (very positive); 0 is neutral. Favorable ≥ +0.30, concerning ≤ −0.30.",
  },
  {
    term: "Competitive position",
    def: "How the model ranks the therapy: first line recommended, among options, second line, not recommended, not mentioned.",
  },
  {
    term: "Citation status",
    def: "Whether the right indication was cited: cited, partial, absent, or wrong indication (content for the wrong disease/indication).",
  },
  {
    term: "Response status",
    def: "Success (complete answer), truncated (cut off at the token limit — partial text kept and still scored), failed (no answer after retries), blocked (provider safety filter).",
  },
];

export default function HowToRead() {
  return (
    <details className="card bg-brand-soft p-4">
      <summary className="cursor-pointer font-semibold text-brand-dark">
        How to read this page
      </summary>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-[max-content_1fr]">
        {DEFS.map((d) => (
          <div key={d.term} className="contents">
            <dt className="text-sm font-bold text-ink">{d.term}</dt>
            <dd className="text-sm text-ink-soft">{d.def}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
