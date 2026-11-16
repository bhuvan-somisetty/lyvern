import type { FeedbackSummary } from "@/lib/api";

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export function FeedbackCard({ summary }: { summary: FeedbackSummary | null }) {
  const decided = summary ? summary.true_positive + summary.false_positive : 0;
  return (
    <section aria-labelledby="precision-heading" className="mt-10">
      <h2 id="precision-heading" className="text-xl font-semibold">
        Measured precision
      </h2>
      {!summary || decided === 0 ? (
        <p className="mt-3 rounded-lg border border-white/10 p-6 text-muted">
          No findings have been labelled yet, so there is no precision number. Open a review and mark
          each finding as a real problem or a false alarm; the figure appears here.
        </p>
      ) : (
        <>
          <p className="mt-3 text-2xl font-semibold tabular-nums">
            {pct(summary.precision ?? 0)}
            <span className="ml-3 text-base font-normal text-muted">
              95% interval {pct(summary.precision_ci_low ?? 0)} to{" "}
              {pct(summary.precision_ci_high ?? 1)}
            </span>
          </p>
          <p className="mt-1 text-sm text-muted">
            From {decided} labelled findings ({summary.true_positive} real, {summary.false_positive}{" "}
            false alarms); {summary.unsure} marked not sure are left out, not guessed.
          </p>
          <div className="mt-4 overflow-x-auto rounded-lg border border-white/10">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Precision by rule</caption>
              <thead className="bg-white/[0.03] text-muted">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">Rule</th>
                  <th scope="col" className="px-4 py-2 font-medium">Real</th>
                  <th scope="col" className="px-4 py-2 font-medium">False alarms</th>
                  <th scope="col" className="px-4 py-2 font-medium">Precision</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_source.map((s) => (
                  <tr key={s.source} className="border-t border-white/10">
                    <td className="px-4 py-2 font-mono">{s.source}</td>
                    <td className="px-4 py-2 tabular-nums">{s.true_positive}</td>
                    <td className="px-4 py-2 tabular-nums">{s.false_positive}</td>
                    <td className="px-4 py-2 tabular-nums">
                      {s.precision === null ? "n/a" : pct(s.precision)}
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
