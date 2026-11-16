// Server-side access to the read-only dashboard API. The token never reaches the browser.

export type Run = {
  id: string;
  repo: string;
  pr_number: number;
  pr_url: string;
  head_sha: string;
  status: string;
  event_posted: string | null;
  findings_count: number | null;
  inline_posted: number | null;
  changes_dismissed: boolean;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type Stats = {
  runs_total: number;
  runs_by_status: Record<string, number>;
  runs_by_event: Record<string, number>;
  findings_total: number;
  inline_comments_total: number;
  deliveries_total: number;
  deliveries_by_status: Record<string, number>;
  last_run_at: string | null;
};

export type Verdict = "true_positive" | "false_positive" | "unsure";
export const VERDICTS: readonly Verdict[] = ["true_positive", "false_positive", "unsure"];

export type Finding = {
  id: string;
  run_id: string;
  file_path: string;
  line_start: number;
  line_end: number;
  severity: string;
  category: string;
  origin: string;
  detection_source: string;
  title: string;
  confidence: number;
  blocking: boolean;
  placed_inline: boolean;
  verdict: Verdict | null;
  note: string | null;
};

export type SourcePrecision = {
  source: string;
  true_positive: number;
  false_positive: number;
  unsure: number;
  precision: number | null;
};

export type FeedbackSummary = {
  findings_total: number;
  labelled: number;
  true_positive: number;
  false_positive: number;
  unsure: number;
  precision: number | null;
  precision_ci_low: number | null;
  precision_ci_high: number | null;
  by_source: SourcePrecision[];
};

export type Result<T> = { ok: true; data: T } | { ok: false; error: string };

const baseUrl = () => process.env.LYVERN_API_URL ?? "http://127.0.0.1:8010";

async function get<T>(path: string): Promise<Result<T>> {
  const token = process.env.LYVERN_API_TOKEN;
  if (!token) {
    return { ok: false, error: "The dashboard API token is not configured (set LYVERN_API_TOKEN)." };
  }
  try {
    const response = await fetch(`${baseUrl()}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (response.status === 401) return { ok: false, error: "The API rejected the token." };
    if (response.status === 503) return { ok: false, error: "The API has no token configured." };
    if (response.status === 404) return { ok: false, error: "Not found." };
    if (!response.ok) return { ok: false, error: `The API returned HTTP ${response.status}.` };
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return { ok: false, error: "The API is not reachable. Is it running?" };
  }
}

export const fetchFindings = (runId: string) =>
  get<Finding[]>(`/api/v1/runs/${encodeURIComponent(runId)}/findings`);
export const fetchFeedback = () => get<FeedbackSummary>("/api/v1/feedback/summary");

/** The one write the dashboard makes: a person's verdict on a finding. Server-side only. */
export async function putVerdict(findingId: string, verdict: Verdict): Promise<Result<Finding>> {
  const token = process.env.LYVERN_API_TOKEN;
  if (!token) return { ok: false, error: "The dashboard API token is not configured." };
  try {
    const response = await fetch(
      `${baseUrl()}/api/v1/findings/${encodeURIComponent(findingId)}/feedback`,
      {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ verdict }),
        cache: "no-store",
      },
    );
    if (!response.ok) return { ok: false, error: `The API returned HTTP ${response.status}.` };
    return { ok: true, data: (await response.json()) as Finding };
  } catch {
    return { ok: false, error: "The API is not reachable. Is it running?" };
  }
}

export const fetchStats = () => get<Stats>("/api/v1/stats");
export const fetchRuns = (limit = 25) => get<Run[]>(`/api/v1/runs?limit=${limit}`);
export const fetchRun = (id: string) => get<Run>(`/api/v1/runs/${encodeURIComponent(id)}`);
