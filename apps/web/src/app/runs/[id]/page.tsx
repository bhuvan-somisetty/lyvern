import Link from "next/link";
import { Suspense } from "react";
import { Loading } from "@/components/Loading";
import { RunDetail } from "@/components/RunDetail";
import { setVerdict } from "@/app/actions";
import { currentSession } from "@/lib/current-session";
import { canLabel } from "@/lib/session";
import { fetchFindings, fetchRun } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo";

async function RunContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [result, findings, who] = await Promise.all([
    fetchRun(id),
    fetchFindings(id),
    DEMO_MODE ? Promise.resolve(null) : currentSession(), // the demo has no sign-in
  ]);
  if (!result.ok) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <Link href="/" className="text-sm text-muted hover:underline">
          Back to all reviews
        </Link>
        <div role="alert" className="mt-6 rounded-lg border border-accent/40 p-4">
          <p className="font-medium">This review could not be loaded.</p>
          <p className="mt-1 text-muted">{result.error}</p>
        </div>
      </main>
    );
  }
  return (
    <RunDetail
      run={result.data}
      findings={findings.ok ? findings.data : []}
      verdictAction={setVerdict}
      canLabel={canLabel(who?.role)}
      demo={DEMO_MODE}
    />
  );
}

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<Loading label="Loading review" />}>
      <RunContent params={params} />
    </Suspense>
  );
}
