import { Suspense } from "react";
import { logout } from "@/app/actions";
import { currentSession } from "@/lib/current-session";
import { Loading } from "@/components/Loading";
import { Overview } from "@/components/Overview";
import { fetchFeedback, fetchRuns, fetchStats } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo";

async function DashboardData() {
  const [stats, runs, feedback, who] = await Promise.all([
    fetchStats(),
    fetchRuns(25),
    fetchFeedback(),
    DEMO_MODE ? Promise.resolve(null) : currentSession(), // the demo has no sign-in
  ]);
  const error = !stats.ok ? stats.error : !runs.ok ? runs.error : undefined;
  return (
    <Overview
      stats={stats.ok ? stats.data : null}
      runs={runs.ok ? runs.data : null}
      error={error}
      feedback={feedback.ok ? feedback.data : null}
      logout={DEMO_MODE ? undefined : logout}
      who={who}
      demo={DEMO_MODE}
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
