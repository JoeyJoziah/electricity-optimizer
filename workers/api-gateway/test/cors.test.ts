import { describe, it, expect } from "vitest";
import {
  handleCorsPreflightOrNull,
  applyCorsHeaders,
} from "../src/middleware/cors";
import type { Env } from "../src/types";

const mockEnv = {
  ALLOWED_ORIGINS: "https://rateshift.app,https://www.rateshift.app",
} as Env;

describe("handleCorsPreflightOrNull", () => {
  it("returns null for non-OPTIONS requests", () => {
    const request = new Request("https://api.rateshift.app/test", {
      method: "GET",
    });
    expect(handleCorsPreflightOrNull(request, mockEnv)).toBeNull();
  });

  it("handles OPTIONS with allowed origin", () => {
    const request = new Request("https://api.rateshift.app/test", {
      method: "OPTIONS",
      headers: { Origin: "https://rateshift.app" },
    });
    const response = handleCorsPreflightOrNull(request, mockEnv);
    expect(response).not.toBeNull();
    expect(response!.status).toBe(204);
    expect(response!.headers.get("Access-Control-Allow-Origin")).toBe(
      "https://rateshift.app"
    );
    expect(response!.headers.get("Access-Control-Allow-Credentials")).toBe(
      "true"
    );
  });

  it("rejects OPTIONS from disallowed origin", () => {
    const request = new Request("https://api.rateshift.app/test", {
      method: "OPTIONS",
      headers: { Origin: "https://evil.com" },
    });
    const response = handleCorsPreflightOrNull(request, mockEnv);
    expect(response).not.toBeNull();
    expect(response!.status).toBe(403);
  });

  it("handles OPTIONS with no Origin header", () => {
    const request = new Request("https://api.rateshift.app/test", {
      method: "OPTIONS",
    });
    const response = handleCorsPreflightOrNull(request, mockEnv);
    expect(response).not.toBeNull();
    expect(response!.status).toBe(204);
  });
});

describe("applyCorsHeaders", () => {
  it("adds CORS headers for allowed origin", () => {
    const request = new Request("https://api.rateshift.app/test", {
      headers: { Origin: "https://rateshift.app" },
    });
    const response = new Response("ok", { status: 200 });
    const result = applyCorsHeaders(response, request, mockEnv);
    expect(result.headers.get("Access-Control-Allow-Origin")).toBe(
      "https://rateshift.app"
    );
    expect(result.headers.get("Access-Control-Allow-Credentials")).toBe(
      "true"
    );
  });

  it("does not add CORS headers for disallowed origin", () => {
    const request = new Request("https://api.rateshift.app/test", {
      headers: { Origin: "https://evil.com" },
    });
    const response = new Response("ok", { status: 200 });
    const result = applyCorsHeaders(response, request, mockEnv);
    expect(result.headers.get("Access-Control-Allow-Origin")).toBeNull();
  });

  it("does not add CORS headers when no Origin", () => {
    const request = new Request("https://api.rateshift.app/test");
    const response = new Response("ok", { status: 200 });
    const result = applyCorsHeaders(response, request, mockEnv);
    expect(result.headers.get("Access-Control-Allow-Origin")).toBeNull();
  });
});
