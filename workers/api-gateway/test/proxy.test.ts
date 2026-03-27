import { describe, it, expect, vi, beforeEach } from "vitest";
import { proxyToOrigin } from "../src/handlers/proxy";
import type { Env } from "../src/types";

// Mock global fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function createMockEnv(overrides: Partial<Env> = {}): Env {
  return {
    ORIGIN_URL: "https://electricity-optimizer.onrender.com",
    INTERNAL_API_KEY: "test-api-key",
    ALLOWED_ORIGINS: "https://rateshift.app",
    CACHE: {} as KVNamespace,
    RATE_LIMITER_STANDARD: { limit: vi.fn() },
    RATE_LIMITER_STRICT: { limit: vi.fn() },
    RATE_LIMITER_INTERNAL: { limit: vi.fn() },
    ...overrides,
  } as Env;
}

function makeRequest(
  url: string,
  init?: RequestInit & { method?: string }
): Request {
  return new Request(url, init);
}

describe("proxyToOrigin", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("URL rewriting", () => {
    it("should rewrite the URL to the origin while preserving path and query", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response('{"ok":true}', { status: 200 })
      );

      const request = makeRequest(
        "https://api.rateshift.app/api/v1/prices/current?region=us_ny"
      );
      const env = createMockEnv();

      await proxyToOrigin(request, env, "req-123", "1.2.3.4");

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [calledUrl] = mockFetch.mock.calls[0];
      expect(calledUrl).toBe(
        "https://electricity-optimizer.onrender.com/api/v1/prices/current?region=us_ny"
      );
    });

    it("should handle paths without query string", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/health");
      await proxyToOrigin(request, createMockEnv(), "req-456", "5.6.7.8");

      const [calledUrl] = mockFetch.mock.calls[0];
      expect(calledUrl).toBe(
        "https://electricity-optimizer.onrender.com/health"
      );
    });
  });

  describe("forwarded headers", () => {
    it("should set X-Forwarded-For to the client IP", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test");
      await proxyToOrigin(request, createMockEnv(), "req-1", "203.0.113.50");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("X-Forwarded-For")).toBe("203.0.113.50");
    });

    it("should set X-Real-IP to the client IP", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test");
      await proxyToOrigin(request, createMockEnv(), "req-1", "203.0.113.50");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("X-Real-IP")).toBe("203.0.113.50");
    });

    it("should set X-Request-ID to the provided requestId", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test");
      await proxyToOrigin(
        request,
        createMockEnv(),
        "unique-request-id-abc",
        "1.2.3.4"
      );

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("X-Request-ID")).toBe("unique-request-id-abc");
    });

    it("should set X-Forwarded-Host to the original hostname", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test");
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("X-Forwarded-Host")).toBe("api.rateshift.app");
    });

    it("should set X-Forwarded-Proto to https", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test");
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("X-Forwarded-Proto")).toBe("https");
    });

    it("should override Host header with origin hostname (SSRF prevention)", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test", {
        headers: { Host: "evil.example.com" },
      });
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("Host")).toBe(
        "electricity-optimizer.onrender.com"
      );
    });
  });

  describe("CF header stripping", () => {
    it("should remove cf-connecting-ip from forwarded request", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test", {
        headers: { "cf-connecting-ip": "1.2.3.4" },
      });
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("cf-connecting-ip")).toBeNull();
    });

    it("should remove cf-ipcountry from forwarded request", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test", {
        headers: { "cf-ipcountry": "US" },
      });
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("cf-ipcountry")).toBeNull();
    });

    it("should remove cf-ray from forwarded request", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test", {
        headers: { "cf-ray": "abc123-EWR" },
      });
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("cf-ray")).toBeNull();
    });

    it("should remove cf-visitor from forwarded request", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test", {
        headers: { "cf-visitor": '{"scheme":"https"}' },
      });
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("cf-visitor")).toBeNull();
    });
  });

  describe("HTTP method handling", () => {
    it("should forward GET requests without body", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response('{"data":"test"}', { status: 200 })
      );

      const request = makeRequest("https://api.rateshift.app/api/v1/prices/current");
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      expect(fetchInit.method).toBe("GET");
      expect(fetchInit.body).toBeUndefined();
    });

    it("should forward POST requests with body", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest(
        "https://api.rateshift.app/api/v1/auth/signin",
        {
          method: "POST",
          body: JSON.stringify({ email: "test@example.com" }),
          headers: { "Content-Type": "application/json" },
        }
      );
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      expect(fetchInit.method).toBe("POST");
      expect(fetchInit.body).toBeDefined();
    });

    it("should forward PUT requests with body", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest(
        "https://api.rateshift.app/api/v1/user/preferences",
        {
          method: "PUT",
          body: JSON.stringify({ theme: "dark" }),
          headers: { "Content-Type": "application/json" },
        }
      );
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      expect(fetchInit.method).toBe("PUT");
      expect(fetchInit.body).toBeDefined();
    });

    it("should forward PATCH requests with body", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest(
        "https://api.rateshift.app/api/v1/user/preferences",
        {
          method: "PATCH",
          body: JSON.stringify({ name: "updated" }),
          headers: { "Content-Type": "application/json" },
        }
      );
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      expect(fetchInit.method).toBe("PATCH");
      expect(fetchInit.body).toBeDefined();
    });

    it("should forward DELETE requests without body", async () => {
      mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));

      const request = makeRequest(
        "https://api.rateshift.app/api/v1/alerts/abc-123",
        { method: "DELETE" }
      );
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      expect(fetchInit.method).toBe("DELETE");
      expect(fetchInit.body).toBeUndefined();
    });
  });

  describe("response passthrough", () => {
    it("should return the origin response status and body", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response('{"prices":[1.23,4.56]}', {
          status: 200,
          statusText: "OK",
        })
      );

      const request = makeRequest("https://api.rateshift.app/api/v1/prices/current");
      const response = await proxyToOrigin(
        request,
        createMockEnv(),
        "req-1",
        "1.2.3.4"
      );

      expect(response.status).toBe(200);
      expect(response.statusText).toBe("OK");
      const body = await response.text();
      expect(body).toBe('{"prices":[1.23,4.56]}');
    });

    it("should pass through error status codes from origin", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response('{"detail":"Not Found"}', {
          status: 404,
          statusText: "Not Found",
        })
      );

      const request = makeRequest(
        "https://api.rateshift.app/api/v1/nonexistent"
      );
      const response = await proxyToOrigin(
        request,
        createMockEnv(),
        "req-1",
        "1.2.3.4"
      );

      expect(response.status).toBe(404);
    });

    it("should pass through 500 errors from origin", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response('{"detail":"Internal server error"}', {
          status: 500,
          statusText: "Internal Server Error",
        })
      );

      const request = makeRequest("https://api.rateshift.app/api/v1/test");
      const response = await proxyToOrigin(
        request,
        createMockEnv(),
        "req-1",
        "1.2.3.4"
      );

      expect(response.status).toBe(500);
    });

    it("should preserve response headers from origin", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("{}", {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "X-Custom-Header": "custom-value",
          },
        })
      );

      const request = makeRequest("https://api.rateshift.app/api/v1/test");
      const response = await proxyToOrigin(
        request,
        createMockEnv(),
        "req-1",
        "1.2.3.4"
      );

      expect(response.headers.get("Content-Type")).toBe("application/json");
      expect(response.headers.get("X-Custom-Header")).toBe("custom-value");
    });
  });

  describe("redirect handling", () => {
    it("should pass through redirects without following them (redirect: manual)", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(null, {
          status: 301,
          statusText: "Moved Permanently",
          headers: { Location: "https://example.com/new-path" },
        })
      );

      const request = makeRequest("https://api.rateshift.app/old-path");
      const response = await proxyToOrigin(
        request,
        createMockEnv(),
        "req-1",
        "1.2.3.4"
      );

      expect(response.status).toBe(301);
      // Verify that fetch was called with redirect: manual
      const [, fetchInit] = mockFetch.mock.calls[0];
      expect(fetchInit.redirect).toBe("manual");
    });

    it("should rewrite Location header to relative path to prevent cross-origin redirects", async () => {
      // FastAPI returns 307 with Location pointing to Render origin
      mockFetch.mockResolvedValueOnce(
        new Response(null, {
          status: 307,
          statusText: "Temporary Redirect",
          headers: {
            Location:
              "https://electricity-optimizer.onrender.com/api/v1/connections/",
          },
        })
      );

      const request = makeRequest(
        "https://api.rateshift.app/api/v1/connections"
      );
      const response = await proxyToOrigin(
        request,
        createMockEnv(),
        "req-1",
        "1.2.3.4"
      );

      expect(response.status).toBe(307);
      // Location must be relative (path only) so the browser resolves
      // against its current origin, preserving session cookies
      expect(response.headers.get("Location")).toBe("/api/v1/connections/");
    });

    it("should not rewrite Location header when it does not match origin", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(null, {
          status: 302,
          statusText: "Found",
          headers: { Location: "https://external-site.com/callback" },
        })
      );

      const request = makeRequest("https://api.rateshift.app/oauth/callback");
      const response = await proxyToOrigin(
        request,
        createMockEnv(),
        "req-1",
        "1.2.3.4"
      );

      expect(response.status).toBe(302);
      // External Location should be left unchanged
      expect(response.headers.get("Location")).toBe(
        "https://external-site.com/callback"
      );
    });
  });

  describe("header preservation", () => {
    it("should forward Authorization header from client to origin", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/user/preferences", {
        headers: { Authorization: "Bearer test-jwt-token" },
      });
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("Authorization")).toBe("Bearer test-jwt-token");
    });

    it("should forward Cookie header for session auth passthrough", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test", {
        headers: { Cookie: "session_id=abc123" },
      });
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("Cookie")).toBe("session_id=abc123");
    });

    it("should forward Content-Type header", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const request = makeRequest("https://api.rateshift.app/api/v1/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      await proxyToOrigin(request, createMockEnv(), "req-1", "1.2.3.4");

      const [, fetchInit] = mockFetch.mock.calls[0];
      const headers = fetchInit.headers as Headers;
      expect(headers.get("Content-Type")).toBe("application/json");
    });
  });
});
