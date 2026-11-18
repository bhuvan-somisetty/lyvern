"use client";

import { useEffect, useRef } from "react";

// The Lyvern lynx, rebuilt as layered SVG from the logo's own geometry (1024 grid) so it can move:
// the head floats, the layers drift at different depths, the eyes follow the pointer, it blinks,
// and a scan line sweeps the visor. Everything stops for reduced motion.
const INK = "#160c10";
const DEEP = "#b01422";
const GLOW = "#ff5448";

const mirror = (pts: number[][]) =>
  pts.map(([x, y]) => `${1024 - x},${y}`).join(" ");
const pts = (p: number[][]) => p.map(([x, y]) => `${x},${y}`).join(" ");

const EAR = [
  [262, 360],
  [292, 150],
  [478, 285],
];
const INNER = [
  [312, 310],
  [322, 215],
  [420, 285],
];
const TUFT = [
  [292, 150],
  [262, 55],
  [338, 128],
];
const RUFF = [
  [215, 540],
  [110, 640],
  [235, 700],
];

export function Mascot({ className = "" }: { className?: string }) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = root.current;
    if (!node) return;
    if (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    let frame = 0;
    let x = 0,
      y = 0,
      tx = 0,
      ty = 0;
    const onMove = (e: PointerEvent) => {
      const box = node.getBoundingClientRect();
      const cx = box.left + box.width / 2;
      const cy = box.top + box.height / 2;
      tx = Math.max(
        -1,
        Math.min(1, (e.clientX - cx) / (window.innerWidth / 2)),
      );
      ty = Math.max(
        -1,
        Math.min(1, (e.clientY - cy) / (window.innerHeight / 2)),
      );
    };
    const tick = () => {
      x += (tx - x) * 0.07;
      y += (ty - y) * 0.07;
      node.style.setProperty("--px", x.toFixed(3));
      node.style.setProperty("--py", y.toFixed(3));
      frame = requestAnimationFrame(tick);
    };
    window.addEventListener("pointermove", onMove);
    frame = requestAnimationFrame(tick);
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div ref={root} className={`mascot ${className}`} aria-hidden>
      <div className="mascot-halo" />
      <div className="mascot-ring mascot-ring-a" />
      <div className="mascot-ring mascot-ring-b" />
      <div className="mascot-float">
        <svg viewBox="0 0 1024 880" className="mascot-svg">
          <defs>
            <linearGradient id="m-cream" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#fffaf2" />
              <stop offset="1" stopColor="#efe2d0" />
            </linearGradient>
            <radialGradient id="m-eye" cx="0.45" cy="0.4" r="0.7">
              <stop offset="0" stopColor="#ff8a7c" />
              <stop offset="0.6" stopColor={GLOW} />
              <stop offset="1" stopColor="#d8302a" />
            </radialGradient>
            <linearGradient id="m-scan" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor={GLOW} stopOpacity="0" />
              <stop offset="0.5" stopColor={GLOW} stopOpacity="0.9" />
              <stop offset="1" stopColor={GLOW} stopOpacity="0" />
            </linearGradient>
            <clipPath id="m-visor">
              <rect x="258" y="430" width="508" height="220" rx="110" />
            </clipPath>
            <filter id="m-soft" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="14" />
            </filter>
          </defs>

          {/* back layer: ears and tufts drift least */}
          <g className="layer-back">
            <polygon points={pts(EAR)} fill="url(#m-cream)" />
            <polygon points={mirror(EAR)} fill="url(#m-cream)" />
            <polygon points={pts(INNER)} fill={DEEP} />
            <polygon points={mirror(INNER)} fill={DEEP} />
            <polygon points={pts(TUFT)} fill={INK} className="tuft-l" />
            <polygon points={mirror(TUFT)} fill={INK} className="tuft-r" />
            <polygon points={pts(RUFF)} fill="url(#m-cream)" />
            <polygon points={mirror(RUFF)} fill="url(#m-cream)" />
          </g>

          {/* head */}
          <g className="layer-mid">
            <rect
              x="196"
              y="262"
              width="632"
              height="550"
              rx="210"
              fill="url(#m-cream)"
            />
            <circle cx="512" cy="340" r="22" fill={DEEP} />
            <circle cx="512" cy="340" r="10" fill={GLOW} className="status" />
            <polygon points="480,690 544,690 512,730" fill={INK} />
            <path
              d="M458 744 a28 30 0 0 0 52 -4 M514 740 a28 30 0 0 0 52 4"
              fill="none"
              stroke={INK}
              strokeWidth="12"
              strokeLinecap="round"
            />
          </g>

          {/* visor and eyes move most: they look at the pointer */}
          <g className="layer-front">
            <rect
              x="258"
              y="430"
              width="508"
              height="220"
              rx="110"
              fill={INK}
            />
            <g clipPath="url(#m-visor)">
              <g className="eyes">
                {[400, 624].map((cx) => (
                  <g key={cx}>
                    <ellipse
                      cx={cx}
                      cy="540"
                      rx="72"
                      ry="78"
                      fill={GLOW}
                      opacity="0.45"
                      filter="url(#m-soft)"
                    />
                    <ellipse
                      cx={cx}
                      cy="540"
                      rx="58"
                      ry="66"
                      fill="url(#m-eye)"
                      className="eye"
                    />
                    <ellipse
                      cx={cx - 16}
                      cy="518"
                      rx="18"
                      ry="22"
                      fill="#ffebe1"
                      className="eye"
                    />
                  </g>
                ))}
              </g>
              <rect
                x="-200"
                y="430"
                width="200"
                height="220"
                fill="url(#m-scan)"
                className="scanline"
              />
            </g>
          </g>
        </svg>
      </div>
      <div className="mascot-shadow" />
    </div>
  );
}
