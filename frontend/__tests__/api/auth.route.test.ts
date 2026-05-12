import { NextRequest } from "next/server";

const mockRequiresTurnstile = jest.fn(() => false);
const mockVerifyTurnstileToken = jest.fn();
const mockHandlerGET = jest.fn();
const mockHandlerPOST = jest.fn();
const mockToNextJsHandler = jest.fn(() => ({
  GET: mockHandlerGET,
  POST: mockHandlerPOST,
}));
const mockGetAuth = jest.fn(() => ({}));

jest.mock("@/lib/auth/server", () => ({
  getAuth: () => mockGetAuth(),
}));
jest.mock("@/lib/auth/turnstile", () => ({
  requiresTurnstile: (...a: unknown[]) => mockRequiresTurnstile(...a),
  verifyTurnstileToken: (...a: unknown[]) => mockVerifyTurnstileToken(...a),
}));
jest.mock("better-auth/next-js", () => ({
  toNextJsHandler: (...a: unknown[]) => mockToNextJsHandler(...a),
}));

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
    clone() {
      return { text: async () => JSON.stringify(this.body) };
    }
  }
  class MockNextRequest {
    url: string;
    headers: Map<string, string | null>;
    constructor(url: string, opts: { headers?: Record<string, string> } = {}) {
      this.url = url;
      this.headers = new Map(Object.entries(opts.headers ?? {}));
    }
  }
  return { NextRequest: MockNextRequest, NextResponse: MockNextResponse };
});

import { GET, POST } from "@/app/api/auth/[...all]/route";

function makeReq(
  url = "http://localhost:3000/api/auth/sign-in",
  headers: Record<string, string> = {},
) {
  return new NextRequest(url, { headers });
}

beforeEach(() => {
  mockRequiresTurnstile.mockReset().mockReturnValue(false);
  mockVerifyTurnstileToken.mockReset();
  mockHandlerGET.mockReset().mockResolvedValue({ status: 200 });
  mockHandlerPOST.mockReset().mockResolvedValue({ status: 200 });
  mockToNextJsHandler.mockClear();
  mockGetAuth.mockClear();
});

describe("GET /api/auth/[...all]", () => {
  it("delegates to handler.GET and returns the response", async () => {
    const res = await GET(makeReq());
    expect(mockHandlerGET).toHaveBeenCalled();
    expect(res.status).toBe(200);
  });

  it("does not check turnstile for GET requests", async () => {
    await GET(makeReq());
    expect(mockVerifyTurnstileToken).not.toHaveBeenCalled();
  });

  it("returns 500 when handler throws", async () => {
    mockHandlerGET.mockRejectedValueOnce(new Error("crash"));
    const res = (await GET(makeReq())) as { status: number; body: unknown };
    expect(res.status).toBe(500);
  });
});

describe("POST /api/auth/[...all] — turnstile bypass (requiresTurnstile=false)", () => {
  it("delegates to handler.POST", async () => {
    const res = await POST(makeReq());
    expect(mockHandlerPOST).toHaveBeenCalled();
    expect(res.status).toBe(200);
  });

  it("returns 500 when handler throws", async () => {
    mockHandlerPOST.mockRejectedValueOnce(new Error("auth crash"));
    const res = (await POST(makeReq())) as { status: number; body: unknown };
    expect(res.status).toBe(500);
  });
});

describe("POST /api/auth/[...all] — turnstile required", () => {
  beforeEach(() => {
    mockRequiresTurnstile.mockReturnValue(true);
  });

  it("returns 400 when turnstile token is missing", async () => {
    mockVerifyTurnstileToken.mockResolvedValueOnce({
      ok: false,
      reason: "missing token",
    });
    const res = (await POST(makeReq())) as { status: number; body: unknown };
    expect(res.status).toBe(400);
    expect(mockHandlerPOST).not.toHaveBeenCalled();
  });

  it("delegates to handler.POST when turnstile passes", async () => {
    mockVerifyTurnstileToken.mockResolvedValueOnce({ ok: true });
    await POST(
      makeReq("http://localhost:3000/api/auth/sign-in", {
        "X-Turnstile-Token": "valid-token",
      }),
    );
    expect(mockHandlerPOST).toHaveBeenCalled();
  });

  it("passes CF-Connecting-IP to verifyTurnstileToken", async () => {
    mockVerifyTurnstileToken.mockResolvedValueOnce({ ok: true });
    await POST(
      makeReq("http://localhost:3000/api/auth/sign-in", {
        "CF-Connecting-IP": "1.2.3.4",
        "X-Turnstile-Token": "tok",
      }),
    );
    expect(mockVerifyTurnstileToken).toHaveBeenCalledWith("tok", "1.2.3.4");
  });
});
