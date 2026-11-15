import { PRODUCT_NAME } from "@/lib/brand";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6">
      <p className="font-mono text-sm text-accent">{PRODUCT_NAME}</p>
      <h1 className="text-4xl font-semibold tracking-tight">
        Pull request intelligence for engineering teams
      </h1>
      <p className="text-lg text-muted">
        No repositories are connected yet. Connect a GitHub repository to see reviews, findings
        and risk analysis here.
      </p>
    </main>
  );
}
