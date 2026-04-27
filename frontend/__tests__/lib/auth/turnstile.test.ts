import { requiresTurnstile, verifyTurnstileToken } from "@/lib/auth/turnstile";

describe("requiresTurnstile", () => {
  it("flags POST to sign-up/email", () => {
    expect(requiresTurnstile("POST", "/api/auth/sign-up/email")).toBe(true);
  });

  it("ignores GET requests", () => {
    expect(requiresTurnstile("GET", "/api/auth/sign-up/email")).toBe(false);
  });

  it("ignores other auth POSTs (sign-in, etc.)", () => {
    expect(requiresTurnstile("POST", "/api/auth/sign-in/email")).toBe(false);
    expect(requiresTurnstile("POST", "/api/auth/sign-out")).toBe(false);
  });
});

describe("verifyTurnstileToken", () => {
  const ORIGINAL_SECRET = process.env.TURNSTILE_SECRET_KEY;
  const fetchMock = jest.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterAll(() => {
    if (ORIGINAL_SECRET === undefined) delete process.env.TURNSTILE_SECRET_KEY;
    else process.env.TURNSTILE_SECRET_KEY = ORIGINAL_SECRET;
  });

  it("passes through when TURNSTILE_SECRET_KEY is unset (dev mode)", async () => {
    delete process.env.TURNSTILE_SECRET_KEY;
    const result = await verifyTurnstileToken("anything");
    expect(result.ok).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects missing token when secret is configured", async () => {
    process.env.TURNSTILE_SECRET_KEY = "secret";
    const result = await verifyTurnstileToken(null);
    expect(result.ok).toBe(false);
    expect(result.reason).toBe("missing_token");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects the dev sentinel when secret is configured", async () => {
    process.env.TURNSTILE_SECRET_KEY = "secret";
    const result = await verifyTurnstileToken(
      "turnstile-not-configured-dev-only",
    );
    expect(result.ok).toBe(false);
    expect(result.reason).toBe("dev_sentinel_in_production");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("calls siteverify with secret + token + remoteip and returns ok on success", async () => {
    process.env.TURNSTILE_SECRET_KEY = "shh";
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
    });

    const result = await verifyTurnstileToken("good-token", "1.2.3.4");

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    );
    const body = (init as RequestInit).body as URLSearchParams;
    expect(body.get("secret")).toBe("shh");
    expect(body.get("response")).toBe("good-token");
    expect(body.get("remoteip")).toBe("1.2.3.4");
  });

  it("returns failure with error codes when CF rejects", async () => {
    process.env.TURNSTILE_SECRET_KEY = "shh";
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: false,
        "error-codes": ["invalid-input-response"],
      }),
    });

    const result = await verifyTurnstileToken("bad-token");
    expect(result.ok).toBe(false);
    expect(result.reason).toBe("siteverify_rejected:invalid-input-response");
  });

  it("returns failure when siteverify is unreachable", async () => {
    process.env.TURNSTILE_SECRET_KEY = "shh";
    fetchMock.mockRejectedValueOnce(new Error("network down"));

    const result = await verifyTurnstileToken("token");
    expect(result.ok).toBe(false);
    expect(result.reason).toBe("siteverify_unreachable");
  });

  it("returns failure on non-2xx siteverify response", async () => {
    process.env.TURNSTILE_SECRET_KEY = "shh";
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({}),
    });

    const result = await verifyTurnstileToken("token");
    expect(result.ok).toBe(false);
    expect(result.reason).toBe("siteverify_http_503");
  });
});
