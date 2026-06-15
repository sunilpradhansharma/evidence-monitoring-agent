interface Props {
  title: string;
  note: string;
}

/** Neutral placeholder for sections that land in a later stage of this build. */
export default function ComingSoon({ title, note }: Props) {
  return (
    <div className="card mt-2 flex flex-col items-center justify-center gap-2 px-8 py-16 text-center">
      <span className="tag tag-muted">Coming soon</span>
      <h2 className="section-title mt-1">{title}</h2>
      <p className="max-w-[52ch] text-sm text-ink-soft">{note}</p>
    </div>
  );
}
