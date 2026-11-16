"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { VERDICTS, putVerdict, verifyLogin, type Verdict } from "@/lib/api";
import {
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  canLabel,
  createSession,
  passwordMatches,
  type Session,
} from "@/lib/session";
import { currentSession } from "@/lib/current-session";
import { loginThrottle } from "@/lib/throttle";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// The owner's break-glass login: the single password from the environment, always an admin.
const OWNER = "owner";

export async function login(formData: FormData): Promise<void> {
  const secret = process.env.LYVERN_SESSION_SECRET;
  if (!secret) redirect("/login?error=config");
  if (!loginThrottle.allowed()) redirect("/login?error=wait");

  const username = String(formData.get("username") ?? "").trim().toLowerCase();
  const given = String(formData.get("password") ?? "");
  let who: Session | null = null;

  const ownerPassword = process.env.LYVERN_DASHBOARD_PASSWORD;
  if (username === OWNER && ownerPassword) {
    if (await passwordMatches(given, ownerPassword, secret)) who = { username: OWNER, role: "admin" };
  } else if (username) {
    const result = await verifyLogin(username, given);
    if (result.ok) who = { username: result.data.username, role: result.data.role };
    else if (result.status === 429) redirect("/login?error=wait");
    else if (result.status === 0) redirect("/login?error=api");
  }

  if (!who) {
    loginThrottle.recordFailure();
    redirect("/login?error=bad");
  }
  loginThrottle.reset();
  const jar = await cookies();
  jar.set(SESSION_COOKIE, await createSession(secret, who), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  redirect("/");
}

export async function logout(): Promise<void> {
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
  redirect("/login");
}

/** Record a verdict on one finding. Checks the session and the role again on every write. */
export async function setVerdict(formData: FormData): Promise<void> {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!canLabel(session.role)) return; // viewers can read but not label
  const findingId = String(formData.get("finding_id") ?? "");
  const runId = String(formData.get("run_id") ?? "");
  const verdict = String(formData.get("verdict") ?? "") as Verdict;
  if (!UUID.test(findingId) || !UUID.test(runId) || !VERDICTS.includes(verdict)) return;
  await putVerdict(findingId, verdict, session.username);
  revalidatePath(`/runs/${runId}`);
  revalidatePath("/");
}
