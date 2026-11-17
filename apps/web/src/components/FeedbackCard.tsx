import type { FeedbackSummary } from "@/lib/api";

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export function FeedbackCard({ summary }: { summary: FeedbackSummary | null }) {
  const decided = summary ? summary.true_positive + summary.false_positive : 0;
  return (
    <section
      aria-labelledby="precision-heading"
      className="h-full rounded-2xl border border-line bg-surface p-6"
    >
      <h2 id="precision-heading" className="font-display text-xl">
        Measured precision
      </h2>
      {!summary || decided === 0 ? (
        <p className="mt-3 text-muted">
          No findings have been labelled yet, so there is no precision number. Open a review and mark
          each finding as a real problem or a false alarm; the figure appears here.
        </p>
      ) : (
        <>
          <p className="font-display mt-3 text-4xl tabular-nums">
            {pct(summary.precision ?? 0)}
            <span className="ml-3 font-sans text-base font-normal text-muted">
              95% interval {pct(summary.precision_ci_low ?? 0)} to{" "}
              {pct(summary.precision_ci_high ?? 1)}
            </span>
          </p>
          <p className="mt-1 text-sm text-muted">
            From {decided} labelled findings ({summary.true_positive} real, {summary.false_positive}{" "}
            false alarms); {summary.unsure} marked not sure are left out, not guessed.
          </p>
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[420px] text-left text-sm">
              <caption className="sr-only">Precision by rule</caption>
              <thead className="text-muted">
                <tr className="border-b border-line">
                  <th scope="col" className="py-2 pr-4 font-medium">Rule</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Real</th>
                  <th scope="col" className="py-2 pr-4 font-medium">False alarms</th>
                  <th scope="col" className="py-2 font-medium">Precision</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_source.map((s) => (
                  <tr key={s.source} className="border-t border-line">
                    <td className="py-2 pr-4 font-mono text-xs">{s.source}</td>
                    <td className="py-2 pr-4 tabular-nums">{s.true_positive}</td>
                    <td className="py-2 pr-4 tabular-nums">{s.false_positive}</td>
                    <td className="py-2 tabular-nums">
                      <span className="flex items-center gap-3">
                        <span className="w-14">{s.precision === null ? "n/a" : pct(s.precision)}</span>
                        <span aria-hidden className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
                          <span
                            className="block h-full rounded-full bg-accent"
                            style={{ width: `${Math.round((s.precision ?? 0) * 100)}%` }}
                          />
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
