"use client";

import { useEffect, useRef, useState } from "react";

export type Chapter = { n: string; title: string; body: string };

// A pinned stage on one side, chapters scrolling past on the other. The chapter in the middle of
// the screen drives the stage. Without JavaScript or with reduced motion every chapter is readable.
export function Story({ chapters }: { chapters: Chapter[] }) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting)
            setActive(Number((e.target as HTMLElement).dataset.i));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_1fr] lg:gap-16">
      <div className="hidden lg:block">
        <div className="sticky top-28">
          <div className="liquid story-stage rounded-[1.75rem] p-8">
            <div className="flex items-baseline justify-between">
              <span className="font-display story-num" key={active}>
                {chapters[active].n}
              </span>
              <span className="font-mono text-xs text-muted">
                {String(active + 1).padStart(2, "0")} /{" "}
                {String(chapters.length).padStart(2, "0")}
              </span>
            </div>
            <div className="story-progress mt-6" aria-hidden>
              <span
                style={{
                  transform: `scaleX(${(active + 1) / chapters.length})`,
                }}
              />
            </div>
            <div className="relative mt-8 h-56">
              <StageArt step={active} />
            </div>
          </div>
        </div>
      </div>

      <ol>
        {chapters.map((c, i) => (
          <li
            key={c.n}
            ref={(el) => {
              refs.current[i] = el;
            }}
            data-i={i}
            className={`story-chapter ${i === active ? "on" : ""}`}
          >
            <span className="font-mono text-xs tracking-[0.2em] text-accent">
              CHAPTER {c.n}
            </span>
            <h3 className="font-display mt-3 text-4xl leading-[1.05] sm:text-5xl">
              {c.title}
            </h3>
            <p className="mt-4 max-w-md text-lg text-muted">{c.body}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function StageArt({ step }: { step: number }) {
  return (
    <>
      <div className={`stage-art ${step === 0 ? "show" : ""}`}>
        <pre className="font-mono text-[12px] leading-6 text-muted">
          {`POST /webhooks/github
x-github-event: pull_request
x-hub-signature-256: sha256=9f2c…
`}
          <span className="text-accent">✓ signature verified</span>
          {`
✓ delivery 4d1e… processed once`}
        </pre>
      </div>
      <div className={`stage-art ${step === 1 ? "show" : ""}`}>
        <pre className="font-mono text-[12px] leading-6">
          <span className="text-muted">@@ -12,4 +12,6 @@</span>
          {"\n"}
          <span className="text-muted"> def total(items):</span>
          {"\n"}
          <span className="diff-add">+ rate = load_rate()</span>
          {"\n"}
          <span className="diff-add">+ return sum(items) * rate</span>
          {"\n"}
          <span className="text-muted">
            {" "}
            # unchanged lines are never blamed
          </span>
        </pre>
      </div>
      <div className={`stage-art ${step === 2 ? "show" : ""}`}>
        <div className="rounded-2xl border border-line bg-black/30 p-4">
          <p className="font-mono text-xs text-muted">app.py : line 14</p>
          <p className="mt-1.5 font-medium">Possible SQL injection</p>
          <p className="mt-1 text-sm text-muted">
            A query string is built from request data.
          </p>
          <span className="chip chip-bad mt-3">high · blocking</span>
        </div>
      </div>
      <div className={`stage-art ${step === 3 ? "show" : ""}`}>
        <div className="flex h-full flex-col justify-center gap-3">
          <span className="chip chip-bad w-fit">Changes requested</span>
          <span className="text-muted">then, after the fix:</span>
          <span className="chip chip-good w-fit">Approved</span>
          <span className="text-xs text-muted">It never merges.</span>
        </div>
      </div>
    </>
  );
}
