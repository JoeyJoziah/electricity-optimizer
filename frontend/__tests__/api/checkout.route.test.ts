import { NextRequest } from "next/server";

const mockFetch = jest.fn();
global.fetch = mockFetch as typeof fetch;

jest.mock("next/server", () => {
  class MockNextResponse {
    status: number;
    body: unknown;
    constructor(body: unknown, init?: { status?: number }) {
      this.body = body;
      this.status = init?.status ?? 200;
    }
    static json(body: unknown, init?: { status?: number }) {
      return new MockNextResponse(body, init);
    }
    async json() {
      return this.body;
    }
  }
  class MockNextRequest {
    private _json: unknown;
    headers: Map<string, string | null>;
    nextUrl: { origin: string };
    constructor(
      url: string,
      options: {
        method?: string;
        body?: string;
        headers?: Record<string, string>;
      } = {},
    ) {
      this._json = options.body ? JSON.parse(options.body) : {};
      this.headers = new Map(Object.entries(options.headers ?? {}));
      const parsed = new URL(url);
      this.nextUrl = { origin: parsed.origin };
    }
    async json() {
      return this._json;
    }
  }
  return {
    NextRequest: MockNextRequest,
    NextResponse: MockNextResponse,
  };
});

import { POST } from "@/app/api/checkout/route";

function makeRequest(authHeader: string | null = "Bearer token123", body = {}) {
  const headers: Record<string, string> = {};
  if (authHeader) headers["authorization"] = authHeader;
  return new NextRequest("http://localhost:3000/api/checkout", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  mockFetch.mockReset();
  process.env.BACKEND_URL = "https://api.test.invalid";
});

afterEach(() => {
  delete process.env.BACKEND_URL;
});

describe("POST /api/checkout", () => {
  it("returns 401 when no authorization header", async () => {
    const res = await POST(makeRequest(null));
    expect(res.status).toBe(401);
  });

  it("returns 401 when auth header does not start with Bearer", async () => {
    const res = await POST(makeRequest("Basic abc123"));
    expect(res.status).toBe(401);
  });

  it("returns 400 when auth header contains newlines (injection)", async () => {
    const res = await POST(makeRequest("Bearer token\ninjected"));
    expect(res.status).toBe(400);
  });

  it("proxies request to backend checkout and returns the checkout_url", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ checkout_url: "https://checkout.stripe.com/123" }),
    });
    const res = await POST(makeRequest());
    const data = await res.json();
    expect(data).toHaveProperty(
      "checkout_url",
      "https://checkout.stripe.com/123",
    );
  });

  it("returns backend error status on non-ok backend response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 402,
      json: async () => ({ error: "Payment required" }),
    });
    const res = await POST(makeRequest());
    expect(res.status).toBe(402);
  });
});
