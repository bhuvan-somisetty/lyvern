import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { CountUp, Tilt } from "@/components/landing/Motion";
import type { Finding, FeedbackSummary, Stats } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";

const REPO_URL = "https://github.com/bhuvan-somisetty/lyvern";

const CAPABILITIES = [
  "Python",
  "JavaScript",
  "TypeScript",
  "Go",
  "Dependency vulnerabilities",
  "Cross-file checks",
  "Merge-conflict help",
  "Optional AI layer",
  "Runs free on GitHub Actions",
];

const STEPS = [
  {
    n: "01",
    title: "A pull request arrives",
    body: "GitHub sends a signed event. Each delivery is verified and processed exactly once.",
  },
  {
    n: "02",
    title: "Only the changed lines are read",
    body: "Static analysers and a diff parser look at what the author touched, so old code is never blamed on them.",
  },
  {
    n: "03",
    title: "Findings land on the exact line",
    body: "Each problem becomes an inline comment with the rule and the reason. Conflicts get their own separate note.",
  },
  {
    n: "04",
    title: "A strict decision",
    body: "Request changes if anything is wrong. Approve only when nothing is left to fix. It never merges.",
  },
];

const TIMELINE = [
  {
    who: "The author",
    title: "Opens a pull request",
    body: "A signed webhook reaches Lyvern. The review starts on the changed lines only.",
    tone: "porcelain",
  },
  {
    who: "Lyvern",
    title: "Requests changes, line by line",
    body: "Each problem is an inline comment with its rule and reason, all in one review.",
    tone: "accent",
  },
  {
    who: "Lyvern",
    title: "Notices the merge conflict",
    body: "A separate note asks for a rebase. It is posted once per commit and never mixed into the code review.",
    tone: "accent",
  },
  {
    who: "The author",
    title: "Fixes it and pushes",
    body: "The review runs again from scratch on the new commit.",
    tone: "porcelain",
  },
  {
    who: "Lyvern",
    title: "Dismisses its own stale review",
    body: "A changes-requested review that no longer applies is withdrawn, so nothing stale blocks the merge.",
    tone: "porcelain",
  },
  {
    who: "Lyvern",
    title: "Approves, only if it is truly clean",
    body: "Zero findings, no conflicts, every file analysed, low risk, and the repository opted in.",
    tone: "porcelain",
  },
];

const QUALITY = [
  { value: "460+", label: "automated Python tests" },
  { value: "33", label: "web tests" },
  { value: "Green", label: "CI on every push" },
  { value: "MIT", label: "open source licence" },
];

const APPROVAL_RULES = [
  "Zero findings of any severity",
  "No merge conflicts",
  "Every changed file was analysed",
  "A low, explainable risk score",
  "The repository opted in to approvals",
];

function Check() {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      aria-hidden
      className="shrink-0 text-accent"
    >
      <path
        d="M4 10.5l4 4 8-9"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-medium uppercase tracking-[0.22em] text-accent">
      {children}
    </p>
  );
}

function Section({
  id,
  eyebrow,
  title,
  lead,
  children,
}: {
  id?: string;
  eyebrow: string;
  title: ReactNode;
  lead?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="mx-auto w-full max-w-6xl px-5 py-24 sm:px-8 sm:py-32"
    >
      <div className="reveal max-w-3xl">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h2 className="font-display mt-4 text-4xl leading-[1.05] sm:text-6xl">
          {title}
        </h2>
        {lead ? (
          <p className="mt-5 text-lg text-muted sm:text-xl">{lead}</p>
        ) : null}
      </div>
      <div className="mt-14">{children}</div>
    </section>
  );
}

function NavBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-[rgba(28,6,16,0.55)] backdrop-blur-xl">
      <nav
        aria-label="Main"
        className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-5 py-3 sm:px-8"
      >
        <Link href="/" className="flex items-center gap-3">
          <Image
            src="/logo.png"
            alt=""
            width={34}
            height={34}
            className="rounded-lg"
            priority
          />
          <span className="font-display text-xl">{PRODUCT_NAME}</span>
        </Link>
        <div className="hidden items-center gap-7 text-sm text-muted md:flex">
          <a href="#how" className="transition-colors hover:text-foreground">
            How it works
          </a>
          <a
            href="#numbers"
            className="transition-colors hover:text-foreground"
          >
            Real numbers
          </a>
          <a href="#honest" className="transition-colors hover:text-foreground">
            Honest results
          </a>
          <a href="#free" className="transition-colors hover:text-foreground">
            Free to run
          </a>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={REPO_URL}
            rel="noreferrer"
            className="hidden text-sm text-muted transition-colors hover:text-foreground sm:inline"
          >
            GitHub
          </a>
          <Link
            href="/dashboard"
            className="btn-accent rounded-full px-4 py-2 text-sm"
          >
            Open the data
          </Link>
        </div>
      </nav>
    </header>
  );
}

function ReviewCard({
  samples,
  findings,
}: {
  samples: Finding[];
  findings: number;
}) {
  const shown = samples.slice(0, 3);
  return (
    <Tilt className="relative mx-auto w-full max-w-md">
      <div className="hero-glow" aria-hidden />
      {shown.slice(1).map((item, i) => (
        <div
          key={item.id}
          aria-hidden
          className="glass absolute inset-x-0 top-0 rounded-3xl"
          style={{
            height: "100%",
            transform: `translate3d(${(i + 1) * 14}px, ${(i + 1) * 18}px, 0) scale(${1 - (i + 1) * 0.04})`,
            opacity: 0.55 - i * 0.2,
            zIndex: -1 - i,
          }}
        />
      ))}
      <div className="tilt-inner glass relative rounded-3xl p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <Image
            src="/logo.png"
            alt=""
            width={36}
            height={36}
            className="rounded-full"
          />
          <div className="leading-tight">
            <p className="text-sm font-medium">lyvern-bot</p>
            <p className="text-xs text-muted">reviewed this pull request</p>
          </div>
          <span className="ml-auto rounded-full border border-accent/50 bg-accent/10 px-3 py-1 text-xs text-accent">
            Changes requested
          </span>
        </div>

        <div className="mt-5 space-y-3">
          {shown.map((item, i) => (
            <div
              key={item.id}
              className={`rounded-2xl border border-line bg-black/25 p-4 ${i > 0 ? "opacity-80" : ""}`}
            >
              <p className="font-mono text-xs text-muted">
                {item.file_path} : line {item.line_start}
              </p>
              <p className="mt-1.5 text-[15px] font-medium">{item.title}</p>
              <div className="mt-2.5 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full border border-line px-2.5 py-0.5 text-muted">
                  {item.severity}
                </span>
                <span className="rounded-full border border-line px-2.5 py-0.5 font-mono text-muted">
                  {item.detection_source}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between rounded-2xl border border-line bg-surface-2 px-4 py-3 text-sm">
          <span className="text-muted">Approval</span>
          <span className="text-accent">
            Blocked until the findings are fixed
          </span>
        </div>
        <p className="mt-3 text-xs text-muted">
          {findings} findings so far across the live reviews.
        </p>
      </div>
      <p className="mt-6 text-center text-xs text-muted">
        Real findings from the live system. File names are hidden.
      </p>
    </Tilt>
  );
}

function Outcome({
  label,
  count,
  total,
  tone,
}: {
  label: string;
  count: number;
  total: number;
  tone: string;
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span>{label}</span>
        <span className="tabular-nums text-muted">
          {count} of {total}
        </span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-[rgba(255,240,213,0.08)]">
        <div
          className="bar h-full rounded-full"
          style={{ width: `${pct}%`, background: tone }}
        />
      </div>
    </div>
  );
}

export function Landing({
  stats,
  feedback,
  samples,
}: {
  stats: Stats | null;
  feedback: FeedbackSummary | null;
  samples: Finding[];
}) {
  const runs = stats?.runs_total ?? 0;
  const events = stats?.runs_by_event ?? {};
  const precision =
    feedback?.precision != null ? feedback.precision * 100 : null;
  const low =
    feedback?.precision_ci_low != null ? feedback.precision_ci_low * 100 : null;
  const high =
    feedback?.precision_ci_high != null
      ? feedback.precision_ci_high * 100
      : null;

  return (
    <>
      <NavBar />
      <main id="top">
        {/* hero */}
        <section className="relative mx-auto grid w-full max-w-6xl items-center gap-14 px-5 pb-20 pt-16 sm:px-8 sm:pt-24 lg:grid-cols-[1.2fr_0.8fr] lg:pb-32 lg:pt-32">
          <div className="rise">
            <p className="inline-flex items-center gap-2 rounded-full border border-line bg-surface-2 px-4 py-1.5 text-xs text-muted">
              <span
                className="h-1.5 w-1.5 rounded-full bg-accent"
                aria-hidden
              />
              Free · Open source · MIT licensed
            </p>
            <h1 className="font-display mt-7 text-[2.5rem] leading-[1.04] sm:text-6xl lg:text-[4.1rem]">
              Reviews that say <em className="text-accent">yes</em> only when
              nothing is left to fix.
            </h1>
            <p className="mt-7 max-w-xl text-lg text-muted sm:text-xl">
              {PRODUCT_NAME} is a GitHub App. It comments on the exact line,
              asks for changes, flags merge conflicts, and measures its own
              accuracy in the open, so you can trust the numbers instead of the
              pitch.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Link
                href="/dashboard"
                className="btn-accent rounded-full px-7 py-3.5 text-base"
              >
                Explore the live data
              </Link>
              <a
                href={REPO_URL}
                rel="noreferrer"
                className="rounded-full border border-line px-7 py-3.5 text-base transition-colors hover:bg-surface-2"
              >
                View the code
              </a>
            </div>
          </div>
          <div className="rise" style={{ animationDelay: "0.15s" }}>
            <ReviewCard
              samples={samples}
              findings={stats?.findings_total ?? 0}
            />
          </div>
        </section>

        {/* capability strip */}
        <div
          aria-label="What it checks"
          className="overflow-hidden border-y border-line py-5 [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]"
        >
          <div className="marquee flex w-max gap-12 text-sm text-muted">
            {[...CAPABILITIES, ...CAPABILITIES].map((item, i) => (
              <span
                key={`${item}-${i}`}
                className="flex items-center gap-12 whitespace-nowrap"
              >
                {item}
                <span className="h-1 w-1 rounded-full bg-accent" aria-hidden />
              </span>
            ))}
          </div>
        </div>

        {/* how it works */}
        <Section
          id="how"
          eyebrow="How it works"
          title={
            <>
              From pull request to decision,{" "}
              <span className="text-muted">in four steps.</span>
            </>
          }
          lead="No black box. Every step is code you can read, test and run yourself."
        >
          <ol className="grid gap-5 sm:grid-cols-2">
            {STEPS.map((step) => (
              <li key={step.n} className="reveal glass rounded-3xl p-7 sm:p-8">
                <span className="font-display text-5xl text-accent">
                  {step.n}
                </span>
                <h3 className="font-display mt-4 text-2xl">{step.title}</h3>
                <p className="mt-3 text-muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </Section>

        {/* approval rule */}
        <Section
          eyebrow="The rule"
          title={
            <>
              Approval is <em className="text-accent">earned</em>, never
              default.
            </>
          }
          lead="Most reviewers drift toward approving. This one is built the opposite way."
        >
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {APPROVAL_RULES.map((rule) => (
              <li
                key={rule}
                className="reveal glass flex items-center gap-3 rounded-2xl px-5 py-4"
              >
                <Check />
                <span>{rule}</span>
              </li>
            ))}
            <li className="reveal glass flex items-center gap-3 rounded-2xl px-5 py-4 text-muted">
              It never merges and never pushes code.
            </li>
          </ul>
        </Section>

        {/* a real pull request lifecycle */}
        <Section
          eyebrow="One pull request, start to finish"
          title={
            <>
              It stays with the change{" "}
              <span className="text-muted">until it is clean.</span>
            </>
          }
          lead="This is the flow the sandbox pull requests exercise, step by step."
        >
          <ol className="relative mx-auto max-w-3xl border-l border-line pl-8">
            {TIMELINE.map((item) => (
              <li key={item.title} className="reveal relative pb-10 last:pb-0">
                <span
                  aria-hidden
                  className="absolute -left-[41px] top-1 flex h-5 w-5 items-center justify-center rounded-full border border-line bg-[#1c0610]"
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{
                      background:
                        item.tone === "accent"
                          ? "var(--accent)"
                          : "var(--porcelain)",
                    }}
                  />
                </span>
                <p className="text-xs uppercase tracking-[0.2em] text-muted">
                  {item.who}
                </p>
                <h3 className="font-display mt-1 text-2xl">{item.title}</h3>
                <p className="mt-2 text-muted">{item.body}</p>
              </li>
            ))}
          </ol>
        </Section>

        {/* real numbers */}
        <Section
          id="numbers"
          eyebrow="Real numbers"
          title={
            <>
              Read from the database.{" "}
              <span className="text-muted">Nothing estimated.</span>
            </>
          }
          lead="These are the actual totals from the live system. Names are hidden, the data is real."
        >
          <div className="grid gap-5 lg:grid-cols-3">
            <div className="reveal glass rounded-3xl p-8 lg:row-span-2">
              <p className="text-sm text-muted">Reviews run</p>
              <p className="font-display mt-3 text-8xl leading-none sm:text-9xl">
                <CountUp value={runs} />
              </p>
              <div className="mt-10 space-y-5">
                <Outcome
                  label="Changes requested"
                  count={events.REQUEST_CHANGES ?? 0}
                  total={runs}
                  tone="var(--accent)"
                />
                <Outcome
                  label="Comment only"
                  count={events.COMMENT ?? 0}
                  total={runs}
                  tone="rgba(255,240,213,0.55)"
                />
                <Outcome
                  label="Approved"
                  count={events.APPROVE ?? 0}
                  total={runs}
                  tone="var(--porcelain)"
                />
              </div>
            </div>
            <div className="reveal glass rounded-3xl p-8">
              <p className="text-sm text-muted">Findings reported</p>
              <p className="font-display mt-3 text-7xl leading-none">
                <CountUp value={stats?.findings_total ?? 0} />
              </p>
            </div>
            <div className="reveal glass rounded-3xl p-8">
              <p className="text-sm text-muted">Inline comments posted</p>
              <p className="font-display mt-3 text-7xl leading-none">
                <CountUp value={stats?.inline_comments_total ?? 0} />
              </p>
            </div>
            <div className="reveal glass rounded-3xl p-8 lg:col-span-2">
              <p className="text-sm text-muted">Findings judged by a person</p>
              <p className="font-display mt-3 text-7xl leading-none">
                <CountUp value={feedback?.labelled ?? 0} />
              </p>
              <p className="mt-4 max-w-lg text-muted">
                Each finding can be marked a real problem or a false alarm.
                Those marks become the accuracy figure below.
              </p>
            </div>
          </div>
        </Section>

        {/* honest results */}
        <Section
          id="honest"
          eyebrow="Measured, not claimed"
          title={
            <>
              The accuracy number is <em className="text-accent">published</em>,
              even when it is low.
            </>
          }
          lead="A reviewer you cannot measure is a reviewer you cannot trust. So the weak spots are on the page."
        >
          <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="reveal glass rounded-3xl p-8">
              <p className="text-sm text-muted">
                Precision on the first labelled run
              </p>
              <p className="font-display mt-3 text-8xl leading-none text-accent">
                {precision != null ? (
                  <CountUp value={precision} suffix="%" />
                ) : (
                  "n/a"
                )}
              </p>
              {low != null && high != null ? (
                <p className="mt-4 text-sm text-muted">
                  95% confidence interval {low.toFixed(0)} to {high.toFixed(0)}
                  %, from{" "}
                  {(feedback?.true_positive ?? 0) +
                    (feedback?.false_positive ?? 0)}{" "}
                  judged findings.
                </p>
              ) : null}
              <p className="mt-6 text-muted">
                That run came before the noisiest rules were switched off. The
                same analysers were then tested on six unseen open-source
                repositories, the false alarms were traced to their causes and
                fixed, and the effect is written down in the repository.
              </p>
            </div>
            <div className="reveal glass rounded-3xl p-8">
              <p className="text-sm text-muted">What the evidence says</p>
              <dl className="mt-5 divide-y divide-line">
                {[
                  [
                    "Synthetic suite",
                    "61 cases, all agree. A regression guard, not real-world accuracy.",
                  ],
                  [
                    "Real pull requests",
                    "Quiet on well-reviewed code: 0 findings on 30 recent PRs.",
                  ],
                  [
                    "Attention model",
                    "AUC 0.70, about the same as change size alone. Advisory only.",
                  ],
                  [
                    "Unseen repositories",
                    "Most false alarms were re-exports and style rules, now fixed.",
                  ],
                ].map(([k, v]) => (
                  <div
                    key={k}
                    className="grid gap-1 py-4 sm:grid-cols-[10rem_1fr] sm:gap-6"
                  >
                    <dt className="font-medium">{k}</dt>
                    <dd className="text-muted">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </Section>

        {/* quality */}
        <section className="mx-auto w-full max-w-6xl px-5 pb-24 sm:px-8">
          <div className="reveal glass grid gap-px overflow-hidden rounded-3xl bg-line sm:grid-cols-2 lg:grid-cols-4">
            {QUALITY.map((q) => (
              <div key={q.label} className="bg-[rgba(28,6,16,0.92)] p-7">
                <p className="font-display text-5xl">{q.value}</p>
                <p className="mt-2 text-sm text-muted">{q.label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* free */}
        <Section
          id="free"
          eyebrow="Free to run"
          title={
            <>
              No server. <span className="text-muted">No bill.</span>
            </>
          }
          lead="Drop one workflow file into a repository. The review runs on GitHub's own free runners."
        >
          <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="reveal glass overflow-hidden rounded-3xl">
              <div className="flex items-center gap-2 border-b border-line px-5 py-3">
                <span className="h-2.5 w-2.5 rounded-full bg-[rgba(255,240,213,0.25)]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[rgba(255,240,213,0.25)]" />
                <span className="h-2.5 w-2.5 rounded-full bg-accent" />
                <span className="ml-3 font-mono text-xs text-muted">
                  .github/workflows/lyvern-review.yml
                </span>
              </div>
              <pre className="overflow-x-auto p-6 font-mono text-[13px] leading-7 text-muted">
                <code>{`on:
  pull_request_target:
    types: [opened, synchronize]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: lyvern action --event "$GITHUB_EVENT_PATH"`}</code>
              </pre>
            </div>
            <div className="reveal glass rounded-3xl p-8">
              <ul className="space-y-4">
                {[
                  "Runs on GitHub's free runners",
                  "Never executes the pull request's code",
                  "MIT licensed, fully open source",
                  "Python, JavaScript, TypeScript and Go",
                ].map((line) => (
                  <li key={line} className="flex items-center gap-3">
                    <Check />
                    {line}
                  </li>
                ))}
              </ul>
              <a
                href={REPO_URL}
                rel="noreferrer"
                className="btn-accent mt-8 inline-block rounded-full px-6 py-3"
              >
                Read the setup guide
              </a>
            </div>
          </div>
        </Section>

        {/* closing */}
        <section className="mx-auto w-full max-w-6xl px-5 pb-28 sm:px-8">
          <div className="reveal glass rounded-[2rem] px-8 py-16 text-center sm:px-16 sm:py-24">
            <h2 className="font-display mx-auto max-w-3xl text-4xl leading-[1.05] sm:text-6xl">
              See every review, every finding, every verdict.
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-lg text-muted">
              The full dashboard is open, read-only, and built from the real
              database.
            </p>
            <Link
              href="/dashboard"
              className="btn-accent mt-9 inline-block rounded-full px-8 py-4 text-base"
            >
              Open the dashboard
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-8 text-sm text-muted sm:px-8">
          <span>
            {PRODUCT_NAME} · built by{" "}
            <a
              href="https://github.com/bhuvan-somisetty"
              rel="noreferrer"
              className="underline-offset-4 hover:underline"
            >
              Bhuvan Somisetty
            </a>
          </span>
          <span className="flex gap-6">
            <a
              href={REPO_URL}
              rel="noreferrer"
              className="hover:text-foreground"
            >
              GitHub
            </a>
            <Link href="/dashboard" className="hover:text-foreground">
              Dashboard
            </Link>
          </span>
        </div>
      </footer>
    </>
  );
}
