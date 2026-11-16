import type { Finding, Verdict } from "@/lib/api";

const VERDICT_LABEL: Record<Verdict, string> = {
  true_positive: "Real problem",
  false_positive: "False alarm",
  unsure: "Not sure",
};

const ORDER: Verdict[] = ["true_positive", "false_positive", "unsure"];

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
      <p className="mt-3 rounded-lg border border-white/10 p-6 text-muted">
        This review stored no findings.
      </p>
    );
  }
  return (
    <ul className="mt-3 flex flex-col gap-3" aria-label="Findings">
      {findings.map((f) => (
        <li key={f.id} className="rounded-lg border border-white/10 p-4">
          <p className="font-medium">{f.title}</p>
          <p className="mt-1 font-mono text-sm text-muted">
            {f.file_path}:{f.line_start} · {f.severity} · {f.category} · {f.detection_source}
            {f.blocking ? " · blocking" : ""}
          </p>
          <p className="mt-2 text-sm">
            <span className="text-muted">Your verdict: </span>
            <span data-testid={`verdict-${f.id}`}>{verdictLabel(f.verdict)}</span>
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
                  className="rounded-md border border-white/20 px-3 py-1 text-sm hover:bg-white/10 aria-pressed:border-accent aria-pressed:text-accent"
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
