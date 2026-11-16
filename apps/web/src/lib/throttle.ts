// A small in-memory brake on password guessing: after too many recent failures, refuse attempts
// for a while. It is per server process, which is enough for a single-owner dashboard.

export class LoginThrottle {
  private failures: number[] = [];

  constructor(
    private readonly maxFailures = 5,
    private readonly windowMs = 60_000,
  ) {}

  private prune(now: number): void {
    this.failures = this.failures.filter((t) => now - t < this.windowMs);
  }

  allowed(now: number = Date.now()): boolean {
    this.prune(now);
    return this.failures.length < this.maxFailures;
  }

  recordFailure(now: number = Date.now()): void {
    this.prune(now);
    this.failures.push(now);
  }

  reset(): void {
    this.failures = [];
  }
}

export const loginThrottle = new LoginThrottle();
