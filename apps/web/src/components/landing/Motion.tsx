"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

const reducedMotion = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Counts up to a real number once it scrolls into view. The server renders the final value. */
export function CountUp({
  value,
  suffix = "",
  decimals = 0,
}: {
  value: number;
  suffix?: string;
  decimals?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);

  useEffect(() => {
    const node = ref.current;
    if (!node || reducedMotion() || typeof IntersectionObserver === "undefined")
      return;
    setShown(0);
    let frame = 0;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min(1, (now - start) / 1400);
          setShown(value * (1 - Math.pow(1 - t, 3)));
          if (t < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [value]);

  return (
    <span
      ref={ref}
      className="tabular-nums"
      aria-label={`${value.toFixed(decimals)}${suffix}`}
    >
      <span aria-hidden>
        {shown.toFixed(decimals)}
        {suffix}
      </span>
    </span>
  );
}

/** A gentle 3D tilt that follows the pointer. Off for touch screens and reduced motion. */
export function Tilt({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const move = (event: React.PointerEvent<HTMLDivElement>) => {
    const node = ref.current;
    if (!node || event.pointerType !== "mouse" || reducedMotion()) return;
    const box = node.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - 0.5;
    const y = (event.clientY - box.top) / box.height - 0.5;
    node.style.setProperty("--ry", `${(x * 7).toFixed(2)}deg`);
    node.style.setProperty("--rx", `${(-y * 7).toFixed(2)}deg`);
    node.style.setProperty("--mx", `${((x + 0.5) * 100).toFixed(1)}%`);
    node.style.setProperty("--my", `${((y + 0.5) * 100).toFixed(1)}%`);
  };

  const leave = () => {
    const node = ref.current;
    if (!node) return;
    node.style.setProperty("--ry", "0deg");
    node.style.setProperty("--rx", "0deg");
  };

  return (
    <div
      ref={ref}
      onPointerMove={move}
      onPointerLeave={leave}
      className={`tilt ${className}`}
    >
      {children}
    </div>
  );
}
