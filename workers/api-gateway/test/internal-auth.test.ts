import { describe, it, expect } from "vitest";
import { validateInternalAuth } from "../src/middleware/internal-auth";
import type { Env } from "../src/types";

function makeEnv(apiKey?: string): Env {
  return {
    INTERNAL_API_KEY: apiKey ?? "",
  } as Env;
}

describe("validateInternalAuth", () => {
  it("returns 503 when edge key is not configured (fail-closed)", async () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test");
    const result = await validateInternalAuth(request, makeEnv(""));
    expect(result).not.toBeNull();
    expect(result!.status).toBe(503);
  });

  it("returns 401 when API key header is missing", async () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test");
    const result = await validateInternalAuth(request, makeEnv("secret-key-123"));
    expect(result).not.toBeNull();
    expect(result!.status).toBe(401);
  });

  it("returns 401 when API key is wrong", async () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test", {
      headers: { "X-API-Key": "wrong-key" },
    });
    const result = await validateInternalAuth(request, makeEnv("secret-key-123"));
    expect(result).not.toBeNull();
    expect(result!.status).toBe(401);
  });

  it("returns null when API key matches", async () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test", {
      headers: { "X-API-Key": "secret-key-123" },
    });
    const result = await validateInternalAuth(request, makeEnv("secret-key-123"));
    expect(result).toBeNull();
  });

  it("returns 401 for different-length keys (constant-time)", async () => {
    const request = new Request("https://api.rateshift.app/api/v1/internal/test", {
      headers: { "X-API-Key": "short" },
    });
    const result = await validateInternalAuth(request, makeEnv("much-longer-secret-key"));
    expect(result).not.toBeNull();
    expect(result!.status).toBe(401);
  });
});
