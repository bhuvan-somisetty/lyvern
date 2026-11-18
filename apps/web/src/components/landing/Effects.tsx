"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

const reducedMotion = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** A soft vermillion light that follows the pointer across the page. Mouse only, off for reduced motion. */
export function Spotlight() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || reducedMotion()) return;
    let frame = 0;
    let x = window.innerWidth / 2;
    let y = window.innerHeight / 3;
    let tx = x;
    let ty = y;
    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      tx = event.clientX;
      ty = event.clientY;
    };
    const tick = () => {
      x += (tx - x) * 0.08;
      y += (ty - y) * 0.08;
      node.style.transform = `translate3d(${x - 300}px, ${y - 300}px, 0)`;
      frame = requestAnimationFrame(tick);
    };
    window.addEventListener("pointermove", onMove);
    frame = requestAnimationFrame(tick);
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  return <div ref={ref} aria-hidden className="spotlight" />;
}

/** A button that leans toward the pointer. Mouse only. */
export function Magnetic({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const move = (event: React.PointerEvent<HTMLSpanElement>) => {
    const node = ref.current;
    if (!node || event.pointerType !== "mouse" || reducedMotion()) return;
    const box = node.getBoundingClientRect();
    const dx = event.clientX - (box.left + box.width / 2);
    const dy = event.clientY - (box.top + box.height / 2);
    node.style.transform = `translate3d(${(dx * 0.18).toFixed(1)}px, ${(dy * 0.28).toFixed(1)}px, 0)`;
  };
  const leave = () => {
    if (ref.current) ref.current.style.transform = "";
  };
  return (
    <span
      ref={ref}
      onPointerMove={move}
      onPointerLeave={leave}
      className={`magnetic inline-block ${className}`}
    >
      {children}
    </span>
  );
}

const BAD = [
  'const express = require("express");',
  "",
  'app.post("/calc", (req, res) => {',
  "  const result = eval(req.body.expr);",
  "  res.json({ result });",
  "});",
];

const GOOD = [
  'const express = require("express");',
  "",
  'app.post("/calc", (req, res) => {',
  "  const result = evaluate(req.body.expr);",
  "  res.json({ result });",
  "});",
];

const STATUS: Record<number, { text: string; cls: string }> = {
  0: { text: "Pull request opened", cls: "chip-idle" },
  1: { text: "Reviewing changed lines", cls: "chip-idle" },
  2: { text: "Changes requested", cls: "chip-bad" },
  3: { text: "Changes requested", cls: "chip-bad" },
  4: { text: "New commit pushed", cls: "chip-idle" },
  5: { text: "Reviewing again from scratch", cls: "chip-idle" },
  6: { text: "Approved", cls: "chip-good" },
};

/**
 * An illustrative, looping walk-through of one review: code arrives, a scan sweeps, a finding lands on the
 * exact line, changes are requested, the author fixes it and the review turns to approved.
 * The snippet is an example, not a recorded review, and the component says so.
 */
export function LiveReview() {
  // The server and reduced-motion visitors see the finished "finding" frame; the loop restarts it from zero.
  const [phase, setPhase] = useState(2);
  const [lines, setLines] = useState(BAD.length);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    if (reducedMotion()) return;
    const clear = () => {
      timers.current.forEach((t) => window.clearTimeout(t));
      timers.current = [];
    };
    const play = () => {
      clear();
      setPhase(0);
      setLines(0);
      const beats: Array<[number, () => void]> = BAD.map((_, i) => [
        500 + i * 260,
        () => setLines(i + 1),
      ]);
      beats.push([2500, () => setPhase(1)]);
      beats.push([3700, () => setPhase(2)]);
      beats.push([7600, () => setPhase(4)]);
      beats.push([8700, () => setPhase(5)]);
      beats.push([9800, () => setPhase(6)]);
      beats.push([14500, play]);
      timers.current = beats.map(([at, run]) => window.setTimeout(run, at));
    };
    timers.current = [window.setTimeout(play, 600)];
    return clear;
  }, []);

  const fixed = phase >= 4;
  const code = fixed ? GOOD : BAD;
  const badLine = 3;
  const status = STATUS[phase];
  const showFinding = phase === 2 || phase === 3;

  return (
    <div className="liquid mx-auto w-full max-w-4xl overflow-hidden rounded-[1.75rem] text-left">
      <div className="flex items-center gap-3 border-b border-line px-5 py-3">
        <span className="flex gap-1.5" aria-hidden>
          <i className="h-2.5 w-2.5 rounded-full bg-[rgba(255,240,213,0.22)]" />
          <i className="h-2.5 w-2.5 rounded-full bg-[rgba(255,240,213,0.22)]" />
          <i className="h-2.5 w-2.5 rounded-full bg-accent" />
        </span>
        <span className="font-mono text-xs text-muted">server.js</span>
        <span
          className={`chip ml-auto ${status.cls}`}
          role="status"
          aria-live="polite"
        >
          {status.text}
        </span>
      </div>

      <div className="relative grid lg:grid-cols-[1.25fr_1fr]">
        <pre
          className="relative overflow-x-auto p-5 font-mono text-[13px] leading-8 sm:p-6"
          aria-label="Example code under review"
        >
          {phase === 1 || phase === 5 ? (
            <span aria-hidden className="scan" />
          ) : null}
          <code>
            {code.map((text, i) => {
              const visible = fixed ? true : i < lines;
              const hot = i === badLine && showFinding;
              const ok = i === badLine && phase >= 6;
              return (
                <span
                  key={i}
                  className={`code-line ${visible ? "on" : ""} ${hot ? "hot" : ""} ${ok ? "ok" : ""}`}
                >
                  <b className="ln">{i + 1}</b>
                  {text || " "}
                  {"\n"}
                </span>
              );
            })}
          </code>
        </pre>

        <div className="relative min-h-44 border-t border-line p-5 sm:p-6 lg:border-l lg:border-t-0">
          <div
            className={`finding ${showFinding ? "show" : ""}`}
            aria-hidden={!showFinding}
          >
            <p className="font-mono text-xs text-muted">server.js : line 4</p>
            <p className="mt-1.5 font-medium">eval() called on request data</p>
            <p className="mt-2 text-sm text-muted">
              Request data reaches eval, so anyone could run code on the server.
            </p>
            <div className="mt-3 flex gap-2 text-xs">
              <span className="chip chip-bad">high</span>
              <span className="chip chip-idle font-mono">lyvern-js:eval</span>
            </div>
          </div>

          <div
            className={`finding ${phase >= 6 ? "show" : ""}`}
            aria-hidden={phase < 6}
          >
            <p className="font-mono text-xs text-muted">All checks</p>
            <p className="mt-1.5 font-medium">Nothing left to fix</p>
            <ul className="mt-3 space-y-1.5 text-sm text-muted">
              <li>Zero findings</li>
              <li>No merge conflicts</li>
              <li>Every changed file analysed</li>
            </ul>
          </div>

          <p
            className={`finding text-sm text-muted ${phase === 0 || phase === 1 ? "show" : ""}`}
            aria-hidden={!(phase === 0 || phase === 1)}
          >
            Reading the changed lines.
          </p>
          <p
            className={`finding text-sm text-muted ${phase === 4 || phase === 5 ? "show" : ""}`}
            aria-hidden={!(phase === 4 || phase === 5)}
          >
            The author replaced eval with a safe parser. Reviewing again from
            scratch.
          </p>
        </div>
      </div>
      <p className="border-t border-line px-5 py-3 text-xs text-muted">
        An illustrative walk-through of one review. The snippet is an example,
        not a recorded pull request.
      </p>
    </div>
  );
}
