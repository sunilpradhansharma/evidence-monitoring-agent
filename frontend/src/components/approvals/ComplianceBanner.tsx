export default function ComplianceBanner() {
  return (
    <div className="mt-4 rounded-xl border border-brand-line bg-brand-soft border-l-4 border-l-brand p-3.5 text-sm text-ink">
      <span className="font-bold text-brand-dark">Compliance:</span> only approved questions are
      ever sent to any model. Every approve or reject is recorded with the reviewer&apos;s name and a
      timestamp in the append-only audit log.
    </div>
  );
}
