import { Suspense } from "react";
import { Loading } from "@/components/Loading";
import { Overview } from "@/components/Overview";
import { fetchRuns, fetchStats } from "@/lib/api";

async function DashboardData() {
  const [stats, runs] = await Promise.all([fetchStats(), fetchRuns(25)]);
  const error = !stats.ok ? stats.error : !runs.ok ? runs.error : undefined;
  return (
    <Overview
      stats={stats.ok ? stats.data : null}
      runs={runs.ok ? runs.data : null}
      error={error}
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
