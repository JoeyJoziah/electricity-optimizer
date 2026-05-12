import { getUserProfile, updateUserProfile } from "@/lib/api/profile";
import { _resetRedirectState } from "@/lib/api/client";

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>;

function mockJson(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: jest.fn().mockResolvedValue(body),
    headers: new Headers(),
    redirected: false,
    type: "basic",
    url: "",
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
    text: jest.fn(),
    bytes: jest.fn(),
  } as unknown as Response;
}

const _profileBase = {
  email: "user@example.com",
  name: "Alice",
  region: "US_CT",
  utility_types: ["electricity"],
  current_supplier_id: "sup-1",
  annual_usage_kwh: 8000,
  onboarding_completed: true,
};

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

describe("getUserProfile", () => {
  it("calls GET /users/profile", async () => {
    mockFetch.mockResolvedValue(mockJson(_profileBase));
    await getUserProfile();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/users/profile");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("returns profile fields", async () => {
    mockFetch.mockResolvedValue(mockJson(_profileBase));
    const result = await getUserProfile();
    expect(result.email).toBe("user@example.com");
    expect(result.region).toBe("US_CT");
    expect(result.onboarding_completed).toBe(true);
  });

  it("handles null optional fields", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        ..._profileBase,
        name: null,
        current_supplier_id: null,
        annual_usage_kwh: null,
      }),
    );
    const result = await getUserProfile();
    expect(result.name).toBeNull();
    expect(result.annual_usage_kwh).toBeNull();
  });
});

describe("updateUserProfile", () => {
  it("calls PUT /users/profile", async () => {
    mockFetch.mockResolvedValue(mockJson({ ..._profileBase, name: "Bob" }));
    await updateUserProfile({ name: "Bob" });
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/users/profile");
    expect(call[1]?.method).toBe("PUT");
  });

  it("returns updated profile", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        ..._profileBase,
        region: "US_NY",
        onboarding_completed: false,
      }),
    );
    const result = await updateUserProfile({
      region: "US_NY",
      onboarding_completed: false,
    });
    expect(result.region).toBe("US_NY");
    expect(result.onboarding_completed).toBe(false);
  });
});
