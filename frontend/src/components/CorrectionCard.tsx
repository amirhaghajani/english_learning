import type { CorrectionItem } from "../api";

interface CorrectionCardProps {
  items: CorrectionItem[];
}

const CATEGORY_LABEL: Record<string, string> = {
  grammar: "Grammar",
  word_choice: "Word choice",
  naturalness: "Naturalness",
};

export function CorrectionCard({ items }: CorrectionCardProps) {
  if (items.length === 0) return null;

  return (
    <section className="corrections" aria-label="Corrections for this turn">
      <header className="corrections__head">
        <span className="corrections__title">Small fixes</span>
        <span className="corrections__count">{items.length}</span>
      </header>
      <ul className="corrections__list">
        {items.map((item, index) => (
          <li
            key={`${item.said}-${index}`}
            className={`corrections__item corrections__item--${item.severity}`}
          >
            <div className="corrections__row">
              <span className="corrections__said">{item.said}</span>
              <span className="corrections__arrow" aria-hidden="true">
                →
              </span>
              <span className="corrections__replacement">{item.replacement}</span>
            </div>
            <div className="corrections__meta">
              <span className="chip">{CATEGORY_LABEL[item.category] ?? item.category}</span>
              {item.severity === "major" ? <span className="chip chip--major">important</span> : null}
              {item.why ? <span className="corrections__why">{item.why}</span> : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}