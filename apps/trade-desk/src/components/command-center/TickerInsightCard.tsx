import Link from "next/link";

type TickerInsightCardProps = {
  symbol: string;
  eyebrow?: string;
  insight: string;
  action?: "buy" | "breakout" | "wait" | "avoid";
  href?: string;
};

const ACTION_LABELS: Record<NonNullable<TickerInsightCardProps["action"]>, string> = {
  buy: "BUY",
  breakout: "BREAKOUT",
  wait: "WAIT",
  avoid: "AVOID",
};

export function TickerInsightCard({
  symbol,
  eyebrow = "Ticker insight",
  insight,
  action,
  href,
}: TickerInsightCardProps) {
  const content = (
    <>
      <div className="td-insight-card__head">
        <span className="td-eyebrow">{eyebrow}</span>
        {action ? (
          <span className={`td-insight-card__action td-insight-card__action--${action}`}>
            {ACTION_LABELS[action]}
          </span>
        ) : null}
      </div>
      <strong className="td-insight-card__symbol">{symbol.toUpperCase()}</strong>
      <p>{insight}</p>
    </>
  );

  return href ? (
    <Link
      className="td-insight-card"
      href={href}
      aria-label={`${symbol.toUpperCase()} ticker insight${action ? `: ${ACTION_LABELS[action]}` : ""}`}
    >
      {content}
    </Link>
  ) : (
    <article className="td-insight-card">{content}</article>
  );
}
