import { Suspense } from "react";
import DashboardPage from "@/app/dashboard/page";
import { Loading } from "@/components/Loading";
import { Landing } from "@/components/landing/Landing";
import type { Finding } from "@/lib/api";
import {
  fetchFeedback,
  fetchFindings,
  fetchRuns,
  fetchStats,
  SNAPSHOT,
} from "@/lib/api";

async function LandingData() {
  const [stats, feedback, runs] = await Promise.all([
    fetchStats(),
    fetchFeedback(),
    fetchRuns(25),
  ]);
  // Up to three different real findings for the hero card (high severity first, posted inline).
  const samples: Finding[] = [];
  if (runs.ok) {
    const pool: Finding[] = [];
    for (const run of runs.data) {
      const found = await fetchFindings(run.id);
      if (found.ok) pool.push(...found.data.filter((f) => f.placed_inline));
    }
    const rank: Record<string, number> = { high: 0, medium: 1, low: 2 };
    pool.sort((a, b) => (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3));
    const seen = new Set<string>();
    for (const f of pool) {
      if (seen.has(f.title)) continue;
      seen.add(f.title);
      samples.push(f);
      if (samples.length === 3) break;
    }
  }
  return (
    <Landing
      stats={stats.ok ? stats.data : null}
      feedback={feedback.ok ? feedback.data : null}
      samples={samples}
    />
  );
}

// The public snapshot opens on the landing page; the private dashboard stays the home page.
export default function Home() {
  if (!SNAPSHOT) return <DashboardPage />;
  return (
    <Suspense fallback={<Loading label="Loading" />}>
      <LandingData />
    </Suspense>
  );
}
