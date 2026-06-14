import type { ReactNode } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";

interface Props {
  title?: string;
  note?: string;
  children: ReactNode;
  delay?: number;
  className?: string;
}

/** A titled section with a subtle fade/slide-in on mount (disabled under reduced motion). */
export default function Section({ title, note, children, delay = 0, className = "" }: Props) {
  const reduced = useReducedMotion();
  const style = reduced ? undefined : { animationDelay: `${delay}ms` };
  const anim = reduced ? "" : "animate-fade-up";
  return (
    <section className={`mt-11 ${anim} ${className}`} style={style}>
      {title && <h2 className="section-title">{title}</h2>}
      {note && <p className="section-note">{note}</p>}
      <div className={title ? "mt-4" : ""}>{children}</div>
    </section>
  );
}
