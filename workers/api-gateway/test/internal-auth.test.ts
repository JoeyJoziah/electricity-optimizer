import { describe, it, expect } from "vitest";
import { validateInternalAuth } from "../src/middleware/internal-auth";
import type { Env } from "../src/types";

function makeEnv(apiKey?: string): Env {
  return {
    INTERNAL_API_KEY: apiKey ?? "",
  } as Env;
}

describe("validateInternalAuth", () => {
  it("returns null (pass-through) when edge key is not configured", () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test");
    const result = validateInternalAuth(request, makeEnv(""));
    expect(result).toBeNull();
  });

  it("returns 401 when API key header is missing", () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test");
    const result = validateInternalAuth(request, makeEnv("secret-key-123"));
    expect(result).not.toBeNull();
    expect(result!.status).toBe(401);
  });

  it("returns 401 when API key is wrong", () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test", {
      headers: { "X-API-Key": "wrong-key" },
    });
    const result = validateInternalAuth(request, makeEnv("secret-key-123"));
    expect(result).not.toBeNull();
    expect(result!.status).toBe(401);
  });

  it("returns null when API key matches", () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test", {
      headers: { "X-API-Key": "secret-key-123" },
    });
    const result = validateInternalAuth(request, makeEnv("secret-key-123"));
    expect(result).toBeNull();
  });

  it("returns 401 for different-length keys (constant-time)", () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test", {
      headers: { "X-API-Key": "short" },
    });
    const result = validateInternalAuth(request, makeEnv("much-longer-secret-key"));
    expect(result).not.toBeNull();
    expect(result!.status).toBe(401);
  });
});
