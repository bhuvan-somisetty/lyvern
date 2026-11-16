import Link from "next/link";
import type { Finding, Run } from "@/lib/api";
import { Findings } from "@/components/Findings";
import { eventLabel } from "@/components/Overview";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-t border-white/10 py-3 sm:flex-row sm:gap-6">
      <dt className="w-48 shrink-0 text-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function RunDetail({
  run,
  findings = [],
  verdictAction,
  canLabel = true,
}: {
  run: Run;
  findings?: Finding[];
  verdictAction?: (formData: FormData) => void | Promise<void>;
  canLabel?: boolean;
}) {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <Link href="/" className="text-sm text-muted hover:underline">
        Back to all reviews
      </Link>
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">
        {run.repo}#{run.pr_number}
      </h1>
      <p className="mt-1 font-mono text-sm text-muted">commit {run.head_sha.slice(0, 12)}</p>

      <dl className="mt-6">
        <Row label="Status">{run.status}</Row>
        <Row label="Result posted">{eventLabel(run.event_posted)}</Row>
        <Row label="Findings">{run.findings_count ?? "not available"}</Row>
        <Row label="Inline comments">{run.inline_posted ?? "not available"}</Row>
        <Row label="Earlier changes-requested review">
          {run.changes_dismissed ? "Dismissed by this bot after the problems were fixed" : "No"}
        </Row>
        <Row label="Started">{run.started_at ?? "not started"}</Row>
        <Row label="Finished">{run.finished_at ?? "not finished"}</Row>
        <Row label="Pull request">
          <a className="text-accent hover:underline" href={run.pr_url} rel="noreferrer">
            Open on GitHub
          </a>
        </Row>
        {run.error ? (
          <Row label="Error">
            <span role="alert" className="font-mono text-sm">{run.error}</span>
          </Row>
        ) : null}
      </dl>

      <h2 className="mt-10 text-xl font-semibold">Findings</h2>
      <p className="mt-1 text-sm text-muted">
        {canLabel
          ? "Mark each one as a real problem or a false alarm. The overview turns your marks into a measured precision figure."
          : "Your account can read reviews but not mark findings. Ask an admin for the reviewer role."}
      </p>
      <Findings findings={findings} runId={run.id} action={canLabel ? verdictAction : undefined} />
    </main>
  );
}
