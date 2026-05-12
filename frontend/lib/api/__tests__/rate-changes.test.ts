import {
  getRateChanges,
  getAlertPreferences,
  upsertAlertPreference,
} from "@/lib/api/rate-changes";
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

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

// ---------------------------------------------------------------------------
// getRateChanges
// ---------------------------------------------------------------------------

describe("getRateChanges", () => {
  it("calls GET /rate-changes", async () => {
    mockFetch.mockResolvedValue(mockJson({ changes: [], total: 0 }));
    await getRateChanges();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rate-changes");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("passes utility_type and region params when provided", async () => {
    mockFetch.mockResolvedValue(mockJson({ changes: [], total: 0 }));
    await getRateChanges({ utility_type: "electricity", region: "US_CT" });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("utility_type=electricity");
    expect(url).toContain("region=US_CT");
  });

  it("passes days and limit params when provided", async () => {
    mockFetch.mockResolvedValue(mockJson({ changes: [], total: 0 }));
    await getRateChanges({ days: 7, limit: 50 });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("days=7");
    expect(url).toContain("limit=50");
  });

  it("omits optional params when not provided", async () => {
    mockFetch.mockResolvedValue(mockJson({ changes: [], total: 0 }));
    await getRateChanges({});
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).not.toContain("utility_type");
    expect(url).not.toContain("region");
    expect(url).not.toContain("days");
    expect(url).not.toContain("limit");
  });

  it("returns changes array", async () => {
    const change = {
      id: "rc-1",
      utility_type: "electricity",
      region: "US_CT",
      supplier: "GridCo",
      previous_price: 0.18,
      current_price: 0.2,
      change_pct: 11.1,
      change_direction: "increase",
      detected_at: "2026-05-01T00:00:00Z",
      recommendation_supplier: null,
      recommendation_price: null,
      recommendation_savings: null,
    };
    mockFetch.mockResolvedValue(mockJson({ changes: [change], total: 1 }));
    const result = await getRateChanges();
    expect(result.changes).toHaveLength(1);
    expect(result.changes[0]!.change_direction).toBe("increase");
  });
});

// ---------------------------------------------------------------------------
// getAlertPreferences
// ---------------------------------------------------------------------------

describe("getAlertPreferences", () => {
  it("calls GET /rate-changes/preferences", async () => {
    mockFetch.mockResolvedValue(mockJson({ preferences: [] }));
    await getAlertPreferences();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rate-changes/preferences");
  });

  it("returns preferences array", async () => {
    const pref = {
      id: "pref-1",
      user_id: "uid-1",
      utility_type: "electricity",
      enabled: true,
      channels: ["email"],
      cadence: "immediate",
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    mockFetch.mockResolvedValue(mockJson({ preferences: [pref] }));
    const result = await getAlertPreferences();
    expect(result.preferences[0]!.utility_type).toBe("electricity");
  });
});

// ---------------------------------------------------------------------------
// upsertAlertPreference
// ---------------------------------------------------------------------------

describe("upsertAlertPreference", () => {
  it("calls PUT /rate-changes/preferences", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        id: "pref-2",
        user_id: "uid-1",
        utility_type: "gas",
        enabled: false,
        channels: ["push"],
        cadence: "daily",
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-02T00:00:00Z",
      }),
    );
    await upsertAlertPreference({ utility_type: "gas", enabled: false });
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/rate-changes/preferences");
    expect(call[1]?.method).toBe("PUT");
  });
});
