import Link from "next/link";
import type { FeedbackSummary, Run, Stats } from "@/lib/api";
import { DecisionBar } from "@/components/DecisionBar";
import { FeedbackCard } from "@/components/FeedbackCard";
import { ReadingGuide } from "@/components/ReadingGuide";
import { SiteHeader } from "@/components/SiteHeader";
import type { Session } from "@/lib/session";

const EVENT_LABEL: Record<string, string> = {
  REQUEST_CHANGES: "Changes requested",
  COMMENT: "Comment only",
  APPROVE: "Approved by policy",
};

const EVENT_DOT: Record<string, string> = {
  REQUEST_CHANGES: "var(--accent)",
  COMMENT: "rgba(255, 240, 213, 0.45)",
  APPROVE: "var(--porcelain)",
};

export function eventLabel(event: string | null): string {
  return event ? (EVENT_LABEL[event] ?? event) : "No review posted";
}

export function EventDot({ event }: { event: string | null }) {
  return (
    <span
      aria-hidden
      className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
      style={{
        background: (event && EVENT_DOT[event]) || "rgba(255, 240, 213, 0.18)",
      }}
    />
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="font-display mt-2 text-4xl tabular-nums">{value}</dd>
    </div>
  );
}

export function RunTable({ runs }: { runs: Run[] }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
      <table className="w-full min-w-[640px] text-left text-sm">
        <caption className="sr-only">Recent review runs</caption>
        <thead className="text-muted">
          <tr className="border-b border-line">
            <th scope="col" className="px-5 py-3 font-medium">
              Pull request
            </th>
            <th scope="col" className="px-5 py-3 font-medium">
              Commit
            </th>
            <th scope="col" className="px-5 py-3 font-medium">
              Result
            </th>
            <th scope="col" className="px-5 py-3 font-medium">
              Findings
            </th>
            <th scope="col" className="px-5 py-3 font-medium">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              className="border-t border-line transition-colors hover:bg-surface-2"
            >
              <td className="px-5 py-3">
                <Link
                  className="text-accent underline-offset-4 hover:underline"
                  href={`/runs/${run.id}`}
                >
                  {run.repo}#{run.pr_number}
                </Link>
              </td>
              <td className="px-5 py-3 font-mono text-muted">
                {run.head_sha.slice(0, 8)}
              </td>
              <td className="px-5 py-3">
                <EventDot event={run.event_posted} />
                {eventLabel(run.event_posted)}
              </td>
              <td className="px-5 py-3 tabular-nums">
                {run.findings_count ?? "-"}
              </td>
              <td className="px-5 py-3 text-muted">{run.status}</td>
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
  feedback = null,
  logout,
  who = null,
}: {
  stats: Stats | null;
  runs: Run[] | null;
  error?: string;
  feedback?: FeedbackSummary | null;
  logout?: () => void | Promise<void>;
  who?: Session | null;
}) {
  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8">
      <SiteHeader who={who} logout={logout} />

      <section className="rise pb-10 pt-12">
        <p className="text-sm text-accent">Pull request intelligence</p>
        <h1 className="font-display mt-3 max-w-3xl text-4xl leading-tight sm:text-5xl">
          Pull request reviews
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">
          Every number on this page is read from the review database. Nothing is
          estimated.
        </p>
      </section>

      {error ? (
        <div
          role="alert"
          className="rounded-2xl border border-accent/40 bg-surface p-5"
        >
          <p className="font-medium">The dashboard could not load its data.</p>
          <p className="mt-1 text-muted">{error}</p>
        </div>
      ) : (
        <>
          <dl
            className="rise grid grid-cols-2 gap-3 lg:grid-cols-4"
            aria-label="Totals"
          >
            <Stat label="Reviews run" value={stats?.runs_total ?? 0} />
            <Stat
              label="Findings reported"
              value={stats?.findings_total ?? 0}
            />
            <Stat
              label="Inline comments"
              value={stats?.inline_comments_total ?? 0}
            />
            <Stat
              label="Webhook deliveries"
              value={stats?.deliveries_total ?? 0}
            />
          </dl>

          <div className="mt-6 grid gap-6 lg:grid-cols-5">
            <div className="lg:col-span-2">
              <DecisionBar events={stats?.runs_by_event ?? {}} />
              <ReadingGuide />
            </div>
            <div className="lg:col-span-3">
              <FeedbackCard summary={feedback} />
            </div>
          </div>

          <h2 className="font-display mt-12 text-2xl">Recent reviews</h2>
          {runs && runs.length > 0 ? (
            <div className="mt-4">
              <RunTable runs={runs} />
            </div>
          ) : (
            <p className="mt-4 rounded-2xl border border-line bg-surface p-6 text-muted">
              No reviews yet. Install the GitHub App on a repository and open a
              pull request; its review will appear here.
            </p>
          )}
        </>
      )}

      <footer className="mt-16 border-t border-line pt-6 text-sm text-muted">
        Lyvern&apos;s reviews are advisory and do not replace human review. AI
        observations are optional, labelled as unverified, and never block a
        merge.
      </footer>
    </main>
  );
}
