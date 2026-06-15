import {
  PROVIDER_EVIDENCE_DEV_NOTE,
  isProviderEvidenceDev,
  targetLabel,
} from "../../targets";

/** A target's human label, with a "dev" badge + explanatory tooltip for the dev stand-in so it is
 *  always visibly distinguished from a general LLM (and never read as "Open Evidence"). */
export default function TargetLabel({
  name,
  className = "",
}: {
  name: string;
  className?: string;
}) {
  const dev = isProviderEvidenceDev(name);
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`} title={dev ? PROVIDER_EVIDENCE_DEV_NOTE : undefined}>
      <span>{targetLabel(name)}</span>
      {dev && (
        <span className="rounded-full border border-wrong-ink/30 bg-wrong-bg px-1.5 py-0.5 text-[0.6rem] font-bold uppercase leading-none tracking-wide text-wrong-ink">
          dev
        </span>
      )}
    </span>
  );
}
