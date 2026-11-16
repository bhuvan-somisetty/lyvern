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

export const fetchStats = () => get<Stats>("/api/v1/stats");
export const fetchRuns = (limit = 25) => get<Run[]>(`/api/v1/runs?limit=${limit}`);
export const fetchRun = (id: string) => get<Run>(`/api/v1/runs/${encodeURIComponent(id)}`);
