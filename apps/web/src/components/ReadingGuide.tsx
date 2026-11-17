// Plain-language help under the decision chart, so a first-time visitor can read the page.

export function ReadingGuide() {
  return (
    <section
      aria-labelledby="guide-heading"
      className="mt-6 rounded-2xl border border-line bg-surface p-6"
    >
      <h2 id="guide-heading" className="font-display text-xl">
        How to read this
      </h2>
      <ul className="mt-4 grid gap-3 text-sm text-muted">
        <li>
          <span className="text-foreground">Changes requested</span> only for
          confident, serious findings.
        </li>
        <li>
          <span className="text-foreground">Approved by policy</span> only when
          there are no findings at all, no merge conflicts, and every file was
          checked.
        </li>
        <li>
          <span className="text-foreground">Precision</span> is the share of
          reported findings that a person marked as a real problem. Findings
          marked &quot;not sure&quot; are left out.
        </li>
      </ul>
    </section>
  );
}
