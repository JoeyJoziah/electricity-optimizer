import {
  getAlerts,
  createAlert,
  updateAlert,
  deleteAlert,
  getAlertHistory,
} from "@/lib/api/alerts";
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
// getAlerts
// ---------------------------------------------------------------------------

describe("getAlerts", () => {
  it("calls GET /alerts", async () => {
    mockFetch.mockResolvedValue(mockJson({ alerts: [], total: 0 }));
    await getAlerts();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/alerts");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("returns alerts and total", async () => {
    const alert = {
      id: "alert-1",
      user_id: "uid-1",
      region: "US_CT",
      currency: "USD",
      price_below: 0.15,
      price_above: null,
      notify_optimal_windows: false,
      is_active: true,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    mockFetch.mockResolvedValue(mockJson({ alerts: [alert], total: 1 }));
    const result = await getAlerts();
    expect(result.total).toBe(1);
    expect(result.alerts[0]!.id).toBe("alert-1");
  });
});

// ---------------------------------------------------------------------------
// createAlert
// ---------------------------------------------------------------------------

describe("createAlert", () => {
  it("calls POST /alerts", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        id: "alert-2",
        user_id: "uid-1",
        region: "US_NY",
        currency: "USD",
        price_below: 0.1,
        price_above: null,
        notify_optimal_windows: true,
        is_active: true,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      }),
    );
    await createAlert({ region: "US_NY", price_below: 0.1 });
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/alerts");
    expect(call[1]?.method).toBe("POST");
  });
});

// ---------------------------------------------------------------------------
// updateAlert
// ---------------------------------------------------------------------------

describe("updateAlert", () => {
  it("calls PUT /alerts/{id}", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        id: "alert-3",
        user_id: "uid-1",
        region: "US_CT",
        currency: "USD",
        price_below: null,
        price_above: 0.25,
        notify_optimal_windows: false,
        is_active: false,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-02T00:00:00Z",
      }),
    );
    await updateAlert("alert-3", { is_active: false });
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/alerts/alert-3");
    expect(call[1]?.method).toBe("PUT");
  });
});

// ---------------------------------------------------------------------------
// deleteAlert
// ---------------------------------------------------------------------------

describe("deleteAlert", () => {
  it("calls DELETE /alerts/{id}", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ deleted: true, alert_id: "alert-4" }),
    );
    const result = await deleteAlert("alert-4");
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/alerts/alert-4");
    expect(call[1]?.method).toBe("DELETE");
    expect(result.deleted).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// getAlertHistory
// ---------------------------------------------------------------------------

describe("getAlertHistory", () => {
  it("calls GET /alerts/history", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ items: [], total: 0, page: 1, page_size: 20, pages: 0 }),
    );
    await getAlertHistory();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/alerts/history");
  });

  it("passes page and page_size params", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ items: [], total: 0, page: 2, page_size: 50, pages: 0 }),
    );
    await getAlertHistory(2, 50);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("page=2");
    expect(url).toContain("page_size=50");
  });

  it("returns items from response", async () => {
    const item = {
      id: "hist-1",
      user_id: "uid-1",
      alert_config_id: "alert-1",
      alert_type: "price_below",
      current_price: 0.12,
      threshold: 0.15,
      region: "US_CT",
      supplier: "GridCo",
      currency: "USD",
      optimal_window_start: null,
      optimal_window_end: null,
      estimated_savings: 20.0,
      triggered_at: "2026-05-01T12:00:00Z",
      email_sent: true,
    };
    mockFetch.mockResolvedValue(
      mockJson({ items: [item], total: 1, page: 1, page_size: 20, pages: 1 }),
    );
    const result = await getAlertHistory();
    expect(result.items).toHaveLength(1);
    expect(result.items[0]!.id).toBe("hist-1");
  });
});
