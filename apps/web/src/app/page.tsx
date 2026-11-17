import { Suspense } from "react";
import { logout } from "@/app/actions";
import { currentSession } from "@/lib/current-session";
import { Loading } from "@/components/Loading";
import { Overview } from "@/components/Overview";
import { fetchFeedback, fetchRuns, fetchStats } from "@/lib/api";

async function DashboardData() {
  const [stats, runs, feedback, who] = await Promise.all([
    fetchStats(),
    fetchRuns(25),
    fetchFeedback(),
    currentSession(),
  ]);
  const error = !stats.ok ? stats.error : !runs.ok ? runs.error : undefined;
  return (
    <Overview
      stats={stats.ok ? stats.data : null}
      runs={runs.ok ? runs.data : null}
      error={error}
      feedback={feedback.ok ? feedback.data : null}
      logout={logout}
      who={who}
    />
  );
}

export default function Home() {
  return (
    <Suspense fallback={<Loading label="Loading reviews" />}>
      <DashboardData />
    </Suspense>
  );
}
