export default function ReviewerField({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const ready = value.trim().length > 0;
  return (
    <div className="mt-4 card p-4">
      <label className="flex flex-col gap-1 text-sm font-semibold text-ink">
        Reviewer name (recorded on every action)
        <input
          type="text"
          className="field max-w-xs"
          placeholder="e.g. j.smith"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label="Reviewer name"
        />
      </label>
      <p className={`mt-2 text-sm ${ready ? "text-fav-ink" : "text-ink-soft"}`}>
        {ready
          ? "Ready — approve or reject any question below."
          : "Enter your reviewer name to enable approve / reject."}
      </p>
    </div>
  );
}
