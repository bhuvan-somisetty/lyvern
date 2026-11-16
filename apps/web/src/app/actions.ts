"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { VERDICTS, putVerdict, type Verdict } from "@/lib/api";
import {
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  createSession,
  passwordMatches,
  verifySession,
} from "@/lib/session";
import { loginThrottle } from "@/lib/throttle";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function login(formData: FormData): Promise<void> {
  const secret = process.env.LYVERN_SESSION_SECRET;
  const expected = process.env.LYVERN_DASHBOARD_PASSWORD;
  if (!secret || !expected) redirect("/login?error=config");
  if (!loginThrottle.allowed()) redirect("/login?error=wait");

  const given = String(formData.get("password") ?? "");
  if (!(await passwordMatches(given, expected, secret))) {
    loginThrottle.recordFailure();
    redirect("/login?error=bad");
  }
  loginThrottle.reset();
  const jar = await cookies();
  jar.set(SESSION_COOKIE, await createSession(secret), {
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

/** Record a verdict on one finding. Checks the session again: the proxy is not the only gate. */
export async function setVerdict(formData: FormData): Promise<void> {
  const jar = await cookies();
  if (!(await verifySession(jar.get(SESSION_COOKIE)?.value, process.env.LYVERN_SESSION_SECRET))) {
    redirect("/login");
  }
  const findingId = String(formData.get("finding_id") ?? "");
  const runId = String(formData.get("run_id") ?? "");
  const verdict = String(formData.get("verdict") ?? "") as Verdict;
  if (!UUID.test(findingId) || !UUID.test(runId) || !VERDICTS.includes(verdict)) return;
  await putVerdict(findingId, verdict);
  revalidatePath(`/runs/${runId}`);
  revalidatePath("/");
}
