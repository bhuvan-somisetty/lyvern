// How the reviews ended: one stacked bar, with the exact counts in a legend underneath.

const PARTS: { key: string; label: string; color: string }[] = [
  { key: "APPROVE", label: "Approved by policy", color: "var(--porcelain)" },
  { key: "COMMENT", label: "Comment only", color: "rgba(255, 240, 213, 0.45)" },
  {
    key: "REQUEST_CHANGES",
    label: "Changes requested",
    color: "var(--accent)",
  },
  {
    key: "none",
    label: "No review posted",
    color: "rgba(255, 240, 213, 0.18)",
  },
];

export function DecisionBar({ events }: { events: Record<string, number> }) {
  const total = PARTS.reduce((sum, p) => sum + (events[p.key] ?? 0), 0);
  return (
    <section
      aria-labelledby="decisions-heading"
      className="rounded-2xl border border-line bg-surface p-6"
    >
      <h2 id="decisions-heading" className="font-display text-xl">
        How reviews ended
      </h2>
      {total === 0 ? (
        <p className="mt-3 text-muted">No finished reviews yet.</p>
      ) : (
        <>
          <div
            className="mt-5 flex h-3 w-full overflow-hidden rounded-full bg-surface-2"
            role="img"
            aria-label={PARTS.filter((p) => events[p.key])
              .map((p) => `${p.label}: ${events[p.key]}`)
              .join(", ")}
          >
            {PARTS.map((p) =>
              events[p.key] ? (
                <span
                  key={p.key}
                  style={{
                    width: `${(100 * events[p.key]) / total}%`,
                    background: p.color,
                  }}
                />
              ) : null,
            )}
          </div>
          <ul className="mt-5 grid gap-2 text-sm">
            {PARTS.filter((p) => events[p.key]).map((p) => (
              <li
                key={p.key}
                className="flex items-center justify-between gap-3"
              >
                <span className="flex items-center gap-2 text-muted">
                  <span
                    aria-hidden
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: p.color }}
                  />
                  {p.label}
                </span>
                <span className="tabular-nums">{events[p.key]}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
