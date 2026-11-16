import { PRODUCT_NAME } from "@/lib/brand";

export const LOGIN_MESSAGES: Record<string, string> = {
  bad: "Wrong password.",
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
    <main className="mx-auto max-w-sm px-6 py-20">
      <p className="font-mono text-sm text-accent">{PRODUCT_NAME}</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Sign in</h1>
      <form action={action} className="mt-6 flex flex-col gap-3">
        <label htmlFor="password" className="text-sm text-muted">
          Dashboard password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          className="rounded-md border border-white/20 bg-transparent px-3 py-2"
        />
        {message ? (
          <p role="alert" className="text-sm text-accent">
            {message}
          </p>
        ) : null}
        <button
          type="submit"
          className="rounded-md bg-accent px-3 py-2 font-medium text-black hover:opacity-90"
        >
          Sign in
        </button>
      </form>
    </main>
  );
}
