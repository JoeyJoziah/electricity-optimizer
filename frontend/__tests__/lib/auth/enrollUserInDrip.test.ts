import { enrollUserInDrip } from "@/lib/auth/drip-enroll";

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  process.env.BACKEND_URL = "https://api.rateshift.app";
  process.env.INTERNAL_API_KEY = "test-api-key";
});

afterEach(() => {
  delete process.env.BACKEND_URL;
  delete process.env.INTERNAL_API_KEY;
});

describe("enrollUserInDrip", () => {
  it("POSTs to the drip enroll endpoint with X-API-Key header", async () => {
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true });

    await enrollUserInDrip("user-123", "alice@example.com", "Alice");

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("https://api.rateshift.app/api/v1/internal/drip/enroll");
    expect(init.method).toBe("POST");
    expect(init.headers["X-API-Key"]).toBe("test-api-key");
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("sends correct JSON body including user_id, email, and name", async () => {
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true });

    await enrollUserInDrip("user-456", "bob@example.com", "Bob");

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body).toEqual({
      user_id: "user-456",
      email: "bob@example.com",
      name: "Bob",
    });
  });

  it("sends null name when user has no display name", async () => {
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true });

    await enrollUserInDrip("user-789", "carol@example.com", null);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.name).toBeNull();
  });

  it("does NOT use X-Internal-API-Key header (regression guard)", async () => {
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true });

    await enrollUserInDrip("user-123", "alice@example.com", "Alice");

    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers["X-Internal-API-Key"]).toBeUndefined();
  });

  it("returns without fetching when BACKEND_URL is missing", async () => {
    delete process.env.BACKEND_URL;

    await enrollUserInDrip("user-123", "alice@example.com", "Alice");

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("returns without fetching when INTERNAL_API_KEY is missing", async () => {
    delete process.env.INTERNAL_API_KEY;

    await enrollUserInDrip("user-123", "alice@example.com", "Alice");

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("swallows fetch errors so sign-up is never blocked", async () => {
    mockFetch.mockRejectedValueOnce(new Error("network failure"));

    await expect(
      enrollUserInDrip("user-123", "alice@example.com", "Alice"),
    ).resolves.toBeUndefined();
  });

  it("swallows non-2xx responses without throwing", async () => {
    mockFetch.mockResolvedValueOnce({ status: 500, ok: false });

    await expect(
      enrollUserInDrip("user-123", "alice@example.com", "Alice"),
    ).resolves.toBeUndefined();
  });
});
