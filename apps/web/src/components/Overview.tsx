import Link from "next/link";
import type { Run, Stats } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";

const EVENT_LABEL: Record<string, string> = {
  REQUEST_CHANGES: "Changes requested",
  COMMENT: "Comment only",
  APPROVE: "Approved by policy",
};

export function eventLabel(event: string | null): string {
  return event ? (EVENT_LABEL[event] ?? event) : "No review posted";
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-4">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

export function RunTable({ runs }: { runs: Run[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-white/10">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Recent review runs</caption>
        <thead className="bg-white/[0.03] text-muted">
          <tr>
            <th scope="col" className="px-4 py-2 font-medium">Pull request</th>
            <th scope="col" className="px-4 py-2 font-medium">Commit</th>
            <th scope="col" className="px-4 py-2 font-medium">Result</th>
            <th scope="col" className="px-4 py-2 font-medium">Findings</th>
            <th scope="col" className="px-4 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-t border-white/10">
              <td className="px-4 py-2">
                <Link className="text-accent hover:underline" href={`/runs/${run.id}`}>
                  {run.repo}#{run.pr_number}
                </Link>
              </td>
              <td className="px-4 py-2 font-mono text-muted">{run.head_sha.slice(0, 8)}</td>
              <td className="px-4 py-2">{eventLabel(run.event_posted)}</td>
              <td className="px-4 py-2 tabular-nums">{run.findings_count ?? "-"}</td>
              <td className="px-4 py-2">{run.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Overview({
  stats,
  runs,
  error,
}: {
  stats: Stats | null;
  runs: Run[] | null;
  error?: string;
}) {
  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <p className="font-mono text-sm text-accent">{PRODUCT_NAME}</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Pull request reviews</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every number on this page is read from the review database. Nothing is estimated.
      </p>

      {error ? (
        <div role="alert" className="mt-8 rounded-lg border border-accent/40 p-4">
          <p className="font-medium">The dashboard could not load its data.</p>
          <p className="mt-1 text-muted">{error}</p>
        </div>
      ) : (
        <>
          <dl className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Totals">
            <Stat label="Reviews run" value={stats?.runs_total ?? 0} />
            <Stat label="Findings reported" value={stats?.findings_total ?? 0} />
            <Stat label="Inline comments" value={stats?.inline_comments_total ?? 0} />
            <Stat label="Webhook deliveries" value={stats?.deliveries_total ?? 0} />
          </dl>

          <h2 className="mt-10 text-xl font-semibold">Recent reviews</h2>
          {runs && runs.length > 0 ? (
            <div className="mt-3">
              <RunTable runs={runs} />
            </div>
          ) : (
            <p className="mt-3 rounded-lg border border-white/10 p-6 text-muted">
              No reviews yet. Install the GitHub App on a repository and open a pull request; its
              review will appear here.
            </p>
          )}
        </>
      )}
    </main>
  );
}
