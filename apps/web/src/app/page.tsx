import { Suspense } from "react";
import { logout } from "@/app/actions";
import { Loading } from "@/components/Loading";
import { Overview } from "@/components/Overview";
import { fetchFeedback, fetchRuns, fetchStats } from "@/lib/api";

async function DashboardData() {
  const [stats, runs, feedback] = await Promise.all([
    fetchStats(),
    fetchRuns(25),
    fetchFeedback(),
  ]);
  const error = !stats.ok ? stats.error : !runs.ok ? runs.error : undefined;
  return (
    <Overview
      stats={stats.ok ? stats.data : null}
      runs={runs.ok ? runs.data : null}
      error={error}
      feedback={feedback.ok ? feedback.data : null}
      logout={logout}
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
