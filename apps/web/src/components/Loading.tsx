export function Loading({ label }: { label: string }) {
  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <p role="status" aria-live="polite" className="text-muted">
        {label}...
      </p>
    </main>
  );
}
