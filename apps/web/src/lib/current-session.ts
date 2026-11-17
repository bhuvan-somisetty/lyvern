import { cookies } from "next/headers";
import { SESSION_COOKIE, verifySession, type Session } from "@/lib/session";

/** The signed-in user of this request, or null. Server-side only (reads the cookie). */
export async function currentSession(): Promise<Session | null> {
  const jar = await cookies();
  return verifySession(
    jar.get(SESSION_COOKIE)?.value,
    process.env.LYVERN_SESSION_SECRET,
  );
}
