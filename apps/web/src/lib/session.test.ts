// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  SESSION_TTL_SECONDS,
  canLabel,
  createSession,
  passwordMatches,
  safeEqual,
  verifySession,
} from "@/lib/session";
import { LoginThrottle } from "@/lib/throttle";

const SECRET = "test-secret-value";
const NOW = 1_800_000_000_000;
const ALICE = { username: "alice", role: "reviewer" } as const;

describe("session cookie", () => {
  it("returns who signed in while the token is fresh and nothing once it has expired", async () => {
    const token = await createSession(SECRET, ALICE, NOW);
    expect(await verifySession(token, SECRET, NOW + 1000)).toEqual(ALICE);
    expect(await verifySession(token, SECRET, NOW + (SESSION_TTL_SECONDS + 1) * 1000)).toBeNull();
  });

  it("supports usernames that contain dots, underscores and dashes", async () => {
    const who = { username: "a.b_c-d", role: "admin" } as const;
    const token = await createSession(SECRET, who, NOW);
    expect(await verifySession(token, SECRET, NOW + 1)).toEqual(who);
  });

  it("cannot be forged by changing the user, the role or the expiry", async () => {
    const token = await createSession(SECRET, ALICE, NOW);
    const [expires, user, role, mac] = token.split(".");
    expect(await verifySession(`${expires}.bob.${role}.${mac}`, SECRET, NOW)).toBeNull();
    expect(await verifySession(`${expires}.${user}.admin.${mac}`, SECRET, NOW)).toBeNull();
    expect(await verifySession(`${Number(expires) + 99999}.${user}.${role}.${mac}`, SECRET, NOW)).toBeNull();
    expect(await verifySession(`${expires}.${user}.${role}.${"0".repeat(mac.length)}`, SECRET, NOW)).toBeNull();
    expect(await verifySession(token, "another-secret", NOW)).toBeNull();
  });

  it("rejects a missing secret, malformed tokens and unknown roles", async () => {
    const token = await createSession(SECRET, ALICE, NOW);
    expect(await verifySession(token, undefined, NOW)).toBeNull();
    expect(await verifySession(token, "", NOW)).toBeNull();
    const [expires, user, , mac] = token.split(".");
    for (const bad of [
      undefined,
      "",
      "abc",
      "1.2.3",
      ".abc",
      "x.y.z.w",
      "-5.alice.admin.abc",
      `${expires}.${user}.root.${mac}`,
      `${expires}..admin.${mac}`,
      `${expires}.Bad Name.admin.${mac}`,
    ]) {
      expect(await verifySession(bad, SECRET, NOW)).toBeNull();
    }
  });

  it("refuses to create a session for an invalid user or role", async () => {
    await expect(createSession(SECRET, { username: "Bad Name", role: "admin" }, NOW)).rejects.toThrow();
    await expect(
      createSession(SECRET, { username: "alice", role: "root" as never }, NOW),
    ).rejects.toThrow();
  });

  it("only reviewers and admins may label", () => {
    expect(canLabel("reviewer")).toBe(true);
    expect(canLabel("admin")).toBe(true);
    expect(canLabel("viewer")).toBe(false);
    expect(canLabel(undefined)).toBe(false);
  });
});

describe("password check", () => {
  it("matches only the exact password and never an empty configured password", async () => {
    expect(await passwordMatches("right horse", "right horse", SECRET)).toBe(true);
    expect(await passwordMatches("right horsf", "right horse", SECRET)).toBe(false);
    expect(await passwordMatches("", "right horse", SECRET)).toBe(false);
    expect(await passwordMatches("", "", SECRET)).toBe(false);
    expect(await passwordMatches("x".repeat(5000), "right horse", SECRET)).toBe(false);
  });

  it("safeEqual compares whole strings", () => {
    expect(safeEqual("abc", "abc")).toBe(true);
    expect(safeEqual("abc", "abd")).toBe(false);
    expect(safeEqual("abc", "abcd")).toBe(false);
  });
});

describe("login throttle", () => {
  it("blocks after repeated failures and recovers when the window passes", () => {
    const t = new LoginThrottle(3, 1000);
    expect(t.allowed(0)).toBe(true);
    t.recordFailure(0);
    t.recordFailure(10);
    expect(t.allowed(20)).toBe(true);
    t.recordFailure(30);
    expect(t.allowed(40)).toBe(false);
    expect(t.allowed(2000)).toBe(true);
  });

  it("reset clears the failures", () => {
    const t = new LoginThrottle(1, 1000);
    t.recordFailure(0);
    expect(t.allowed(1)).toBe(false);
    t.reset();
    expect(t.allowed(2)).toBe(true);
  });
});
