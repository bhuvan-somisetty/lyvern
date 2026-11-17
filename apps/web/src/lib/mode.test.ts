import { describe, expect, it } from "vitest";
import { isSnapshot } from "@/lib/mode";

describe("isSnapshot", () => {
  it("is on when asked for", () => {
    expect(isSnapshot({ LYVERN_SNAPSHOT: "1" })).toBe(true);
  });
  it("is on for a Vercel deploy without a private API", () => {
    expect(isSnapshot({ VERCEL: "1" })).toBe(true);
  });
  it("stays off locally and when a private API is configured", () => {
    expect(isSnapshot({})).toBe(false);
    expect(isSnapshot({ VERCEL: "1", LYVERN_API_URL: "https://api" })).toBe(
      false,
    );
    expect(isSnapshot({ VERCEL: "1", LYVERN_SNAPSHOT: "0" })).toBe(false);
  });
});
