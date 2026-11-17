import Image from "next/image";
import { PRODUCT_NAME } from "@/lib/brand";

export const LOGIN_MESSAGES: Record<string, string> = {
  bad: "Wrong username or password.",
  api: "The sign-in service is not reachable. Is the API running?",
  wait: "Too many attempts. Wait a minute and try again.",
  config:
    "Login is not configured on the server (set LYVERN_DASHBOARD_PASSWORD and LYVERN_SESSION_SECRET).",
};

export function LoginForm({
  error,
  action,
}: {
  error?: string;
  action: (formData: FormData) => void | Promise<void>;
}) {
  const message = error ? (LOGIN_MESSAGES[error] ?? "Could not sign in.") : null;
  return (
    <main className="mx-auto w-full max-w-sm px-6 py-20">
      <div className="rise rounded-3xl border border-line bg-surface p-8">
        <div className="flex items-center gap-3">
          <Image src="/logo.png" alt="" width={44} height={44} className="rounded-xl" priority />
          <span className="font-display text-2xl">{PRODUCT_NAME}</span>
        </div>
        <h1 className="font-display mt-8 text-4xl">Sign in</h1>
        <p className="mt-2 text-sm text-muted">For the people who run the review bot.</p>
        <form action={action} className="mt-6 flex flex-col gap-3">
          <label htmlFor="username" className="text-sm text-muted">
            Username
          </label>
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            required
            className="rounded-lg border border-line bg-black/25 px-3 py-2.5"
          />
          <label htmlFor="password" className="text-sm text-muted">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className="rounded-lg border border-line bg-black/25 px-3 py-2.5"
          />
          {message ? (
            <p role="alert" className="text-sm text-accent">
              {message}
            </p>
          ) : null}
          <button type="submit" className="btn-accent mt-2 rounded-lg px-3 py-2.5">
            Sign in
          </button>
        </form>
      </div>
    </main>
  );
}
