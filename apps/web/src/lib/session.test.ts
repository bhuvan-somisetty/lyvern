// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  createSession,
  passwordMatches,
  safeEqual,
  verifySession,
  SESSION_TTL_SECONDS,
} from "@/lib/session";
import { LoginThrottle } from "@/lib/throttle";

const SECRET = "test-secret-value";
const NOW = 1_800_000_000_000;

describe("session cookie", () => {
  it("accepts a fresh token and rejects it once it has expired", async () => {
    const token = await createSession(SECRET, NOW);
    expect(await verifySession(token, SECRET, NOW + 1000)).toBe(true);
    expect(await verifySession(token, SECRET, NOW + (SESSION_TTL_SECONDS + 1) * 1000)).toBe(false);
  });

  it("rejects tampering, another secret, malformed input and a missing secret", async () => {
    const token = await createSession(SECRET, NOW);
    const [expires, mac] = token.split(".");
    expect(await verifySession(`${Number(expires) + 99999}.${mac}`, SECRET, NOW)).toBe(false);
    expect(await verifySession(`${expires}.${"0".repeat(mac.length)}`, SECRET, NOW)).toBe(false);
    expect(await verifySession(token, "another-secret", NOW)).toBe(false);
    expect(await verifySession(token, undefined, NOW)).toBe(false);
    expect(await verifySession(token, "", NOW)).toBe(false);
    for (const bad of [undefined, "", "abc", "1.2.3", ".abc", `${expires}.`, "x.y", "-5.abc"]) {
      expect(await verifySession(bad, SECRET, NOW)).toBe(false);
    }
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
