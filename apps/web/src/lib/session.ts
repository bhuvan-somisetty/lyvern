// Password login for the dashboard: a signed, expiring cookie. Uses only Web Crypto so the same
// code runs in the proxy (edge-style) and in server actions. Fails closed when not configured.

export const SESSION_COOKIE = "lyvern_session";
export const SESSION_TTL_SECONDS = 8 * 60 * 60;

const encoder = new TextEncoder();

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return Array.from(new Uint8Array(signature))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/** Compares in time that does not depend on where the strings first differ. */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i += 1) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}

export async function createSession(
  secret: string,
  now: number = Date.now(),
  ttlSeconds: number = SESSION_TTL_SECONDS,
): Promise<string> {
  const expires = Math.floor(now / 1000) + ttlSeconds;
  return `${expires}.${await hmacHex(secret, `lyvern-session:${expires}`)}`;
}

export async function verifySession(
  token: string | undefined,
  secret: string | undefined,
  now: number = Date.now(),
): Promise<boolean> {
  if (!token || !secret) return false;
  const parts = token.split(".");
  if (parts.length !== 2) return false;
  const [expiresText, mac] = parts;
  if (!/^\d{1,12}$/.test(expiresText) || !mac) return false;
  const expires = Number(expiresText);
  if (expires * 1000 <= now) return false;
  return safeEqual(mac, await hmacHex(secret, `lyvern-session:${expires}`));
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
