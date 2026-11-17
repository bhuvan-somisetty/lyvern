// Login for the dashboard: a signed, expiring cookie that carries the username and role. Uses only
// Web Crypto so the same code runs in the proxy and in server actions. Fails closed when the
// signing secret is not configured. The role is re-checked by the server on every write.

export const SESSION_COOKIE = "lyvern_session";
export const SESSION_TTL_SECONDS = 8 * 60 * 60;

export type Role = "viewer" | "reviewer" | "admin";
export const ROLES: readonly Role[] = ["viewer", "reviewer", "admin"];
export type Session = { username: string; role: Role };

const USERNAME = /^[a-z0-9][a-z0-9._-]{1,31}$/;
const encoder = new TextEncoder();

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(message),
  );
  return Array.from(new Uint8Array(signature))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/** Compares in time that does not depend on where the strings first differ. */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i += 1)
    difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}

export function canLabel(role: Role | undefined): boolean {
  return role === "reviewer" || role === "admin";
}

export async function createSession(
  secret: string,
  who: Session,
  now: number = Date.now(),
  ttlSeconds: number = SESSION_TTL_SECONDS,
): Promise<string> {
  if (!USERNAME.test(who.username) || !ROLES.includes(who.role)) {
    throw new Error("invalid session subject");
  }
  const expires = Math.floor(now / 1000) + ttlSeconds;
  const mac = await hmacHex(
    secret,
    `lyvern-session:${expires}:${who.username}:${who.role}`,
  );
  return `${expires}.${who.username}.${who.role}.${mac}`;
}

export async function verifySession(
  token: string | undefined,
  secret: string | undefined,
  now: number = Date.now(),
): Promise<Session | null> {
  if (!token || !secret) return null;
  const parts = token.split(".");
  // the username may contain dots, so the last two fields are role and mac, the first is expiry
  if (parts.length < 4) return null;
  const expiresText = parts[0];
  const mac = parts[parts.length - 1];
  const role = parts[parts.length - 2] as Role;
  const username = parts.slice(1, -2).join(".");
  if (!/^\d{1,12}$/.test(expiresText) || !mac || !ROLES.includes(role))
    return null;
  if (!USERNAME.test(username)) return null;
  const expires = Number(expiresText);
  if (expires * 1000 <= now) return null;
  const expected = await hmacHex(
    secret,
    `lyvern-session:${expires}:${username}:${role}`,
  );
  return safeEqual(mac, expected) ? { username, role } : null;
}

/** Both sides are hashed first, so the comparison never depends on the password length. */
export async function passwordMatches(
  given: string,
  expected: string,
  secret: string,
): Promise<boolean> {
  if (!expected) return false;
  const [a, b] = await Promise.all([
    hmacHex(secret, `password:${given}`),
    hmacHex(secret, `password:${expected}`),
  ]);
  return safeEqual(a, b);
}
