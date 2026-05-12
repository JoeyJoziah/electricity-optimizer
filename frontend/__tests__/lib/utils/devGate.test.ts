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
