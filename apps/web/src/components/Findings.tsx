import type { Finding, Verdict } from "@/lib/api";

const VERDICT_LABEL: Record<Verdict, string> = {
  true_positive: "Real problem",
  false_positive: "False alarm",
  unsure: "Not sure",
};

const ORDER: Verdict[] = ["true_positive", "false_positive", "unsure"];

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-accent text-accent",
  high: "border-accent/70 text-accent",
  medium: "border-foreground/50 text-foreground",
  low: "border-line text-muted",
  info: "border-line text-muted",
};

export function verdictLabel(verdict: Verdict | null): string {
  return verdict ? VERDICT_LABEL[verdict] : "Not reviewed yet";
}

export function Findings({
  findings,
  runId,
  action,
}: {
  findings: Finding[];
  runId: string;
  action?: (formData: FormData) => void | Promise<void>;
}) {
  if (findings.length === 0) {
    return (
      <p className="mt-4 rounded-2xl border border-line bg-surface p-6 text-muted">
        This review stored no findings.
      </p>
    );
  }
  return (
    <ul className="mt-4 flex flex-col gap-3" aria-label="Findings">
      {findings.map((f) => (
        <li
          key={f.id}
          className="rounded-2xl border border-line bg-surface p-5"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="max-w-3xl font-medium">{f.title}</p>
            <span className="flex flex-wrap items-center gap-2 text-xs">
              <span
                className={`rounded-full border px-2.5 py-0.5 ${SEVERITY_STYLE[f.severity] ?? SEVERITY_STYLE.low}`}
              >
                {f.severity}
              </span>
              {f.blocking ? (
                <span className="rounded-full border border-accent px-2.5 py-0.5 text-accent">
                  blocking
                </span>
              ) : null}
            </span>
          </div>
          <p className="mt-2 font-mono text-sm text-muted">
            {f.file_path}:{f.line_start} · {f.severity} · {f.category} ·{" "}
            {f.detection_source}
            {f.blocking ? " · blocking" : ""}
          </p>
          <p className="mt-3 text-sm">
            <span className="text-muted">Your verdict: </span>
            <span data-testid={`verdict-${f.id}`}>
              {verdictLabel(f.verdict)}
            </span>
          </p>
          {action ? (
            <form action={action} className="mt-3 flex flex-wrap gap-2">
              <input type="hidden" name="finding_id" value={f.id} />
              <input type="hidden" name="run_id" value={runId} />
              {ORDER.map((v) => (
                <button
                  key={v}
                  type="submit"
                  name="verdict"
                  value={v}
                  aria-pressed={f.verdict === v}
                  className="rounded-full border border-line px-4 py-1.5 text-sm transition-colors hover:bg-surface-2 aria-pressed:border-accent aria-pressed:bg-accent aria-pressed:text-foreground"
                >
                  {VERDICT_LABEL[v]}
                </button>
              ))}
            </form>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
