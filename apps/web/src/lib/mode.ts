/**
 * The public site runs as a read-only snapshot: no login, no writes, real anonymised data.
 * It is on when LYVERN_SNAPSHOT=1, and also on any Vercel deployment that has no private API
 * configured, so a deploy can never fall back to the sign-in page by accident.
 */
export const isSnapshot = (
  env: Record<string, string | undefined> = process.env,
) =>
  env.LYVERN_SNAPSHOT === "1" ||
  (env.VERCEL === "1" && !env.LYVERN_API_URL && env.LYVERN_SNAPSHOT !== "0");
