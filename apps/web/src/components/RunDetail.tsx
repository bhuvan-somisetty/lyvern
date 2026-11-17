import Link from "next/link";
import type { Finding, Run } from "@/lib/api";
import { EventDot, eventLabel } from "@/components/Overview";
import { Findings } from "@/components/Findings";
import { SiteHeader } from "@/components/SiteHeader";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-t border-line py-3 sm:flex-row sm:gap-6">
      <dt className="w-52 shrink-0 text-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function RunDetail({
  run,
  findings = [],
  verdictAction,
  canLabel = true,
  demo = false,
}: {
  run: Run;
  findings?: Finding[];
  verdictAction?: (formData: FormData) => void | Promise<void>;
  canLabel?: boolean;
  demo?: boolean;
}) {
  return (
    <main className="mx-auto w-full max-w-4xl px-5 py-8 sm:px-8">
      <SiteHeader demo={demo} />
      <Link href="/" className="mt-8 inline-block text-sm text-muted underline-offset-4 hover:underline">
        Back to all reviews
      </Link>
      <h1 className="font-display mt-4 text-3xl sm:text-4xl">
        {run.repo}#{run.pr_number}
      </h1>
      <p className="mt-2 font-mono text-sm text-muted">commit {run.head_sha.slice(0, 12)}</p>

      <dl className="mt-8 rounded-2xl border border-line bg-surface px-6 py-2">
        <Row label="Status">{run.status}</Row>
        <Row label="Result posted">
          <EventDot event={run.event_posted} />
          {eventLabel(run.event_posted)}
        </Row>
        <Row label="Findings">{run.findings_count ?? "not available"}</Row>
        <Row label="Inline comments">{run.inline_posted ?? "not available"}</Row>
        <Row label="Earlier changes-requested review">
          {run.changes_dismissed ? "Dismissed by this bot after the problems were fixed" : "No"}
        </Row>
        <Row label="Started">{run.started_at ?? "not started"}</Row>
        <Row label="Finished">{run.finished_at ?? "not finished"}</Row>
        <Row label="Pull request">
          <a className="text-accent underline-offset-4 hover:underline" href={run.pr_url} rel="noreferrer">
            Open on GitHub
          </a>
        </Row>
        {run.error ? (
          <Row label="Error">
            <span role="alert" className="font-mono text-sm">
              {run.error}
            </span>
          </Row>
        ) : null}
      </dl>

      <h2 className="font-display mt-12 text-2xl">Findings</h2>
      <p className="mt-1 text-sm text-muted">
        {demo
          ? "This is a read-only demo with sample data, so verdicts cannot be saved here."
          : canLabel
            ? "Mark each one as a real problem or a false alarm. The overview turns your marks into a measured precision figure."
            : "Your account can read reviews but not mark findings. Ask an admin for the reviewer role."}
      </p>
      <Findings findings={findings} runId={run.id} action={canLabel && !demo ? verdictAction : undefined} />
    </main>
  );
}
