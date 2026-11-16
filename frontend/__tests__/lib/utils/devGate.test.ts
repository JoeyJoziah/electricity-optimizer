import { isDevMode } from "@/lib/utils/devGate";

describe("isDevMode", () => {
  const originalEnv = process.env.NODE_ENV;

  afterEach(() => {
    Object.defineProperty(process.env, "NODE_ENV", {
      value: originalEnv,
      configurable: true,
    });
  });

  it("returns false in test environment", () => {
    expect(isDevMode()).toBe(false);
  });

  it("returns true when NODE_ENV is development", () => {
    Object.defineProperty(process.env, "NODE_ENV", {
      value: "development",
      configurable: true,
    });
    expect(isDevMode()).toBe(true);
  });

  it("returns false when NODE_ENV is production", () => {
    Object.defineProperty(process.env, "NODE_ENV", {
      value: "production",
      configurable: true,
    });
    expect(isDevMode()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/utils/devGate.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  const env = process.env as { NODE_ENV: string };

  describe("isDevMode", () => {
    const originalNodeEnv = env.NODE_ENV;

    afterEach(() => {
      env.NODE_ENV = originalNodeEnv;
    });

    it("returns false when NODE_ENV is test", () => {
      env.NODE_ENV = "test";

      expect(isDevMode()).toBe(false);
    });
  });
}
