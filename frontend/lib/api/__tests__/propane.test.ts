import {
  getPropanePrices,
  getPropaneHistory,
  getPropaneComparison,
  getPropaneTiming,
} from "@/lib/api/propane";
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

describe("getPropanePrices", () => {
  it("calls GET /rates/propane without filter", async () => {
    mockFetch.mockResolvedValue(mockJson({ prices: [], tracked_states: [] }));
    await getPropanePrices();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/propane");
    expect(url).not.toContain("state=");
  });

  it("passes state param when provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ prices: [], tracked_states: ["CT"] }),
    );
    await getPropanePrices("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("state=CT");
  });
});

describe("getPropaneHistory", () => {
  it("calls GET /rates/propane/history with state", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "CT", weeks: 4, history: [], comparison: null }),
    );
    await getPropaneHistory("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/propane/history");
    expect(url).toContain("state=CT");
  });

  it("passes weeks param when provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "CT", weeks: 12, history: [], comparison: null }),
    );
    await getPropaneHistory("CT", 12);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("weeks=12");
  });
});

describe("getPropaneComparison", () => {
  it("calls GET /rates/propane/compare or similar endpoint", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        state: "CT",
        price_per_gallon: 2.85,
        national_avg: 2.6,
        difference_pct: 9.6,
        estimated_monthly_cost: 114.0,
        estimated_annual_cost: 1368.0,
      }),
    );
    await getPropaneComparison("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("state=CT");
  });
});

describe("getPropaneTiming", () => {
  it("calls endpoint with state and returns timing advice", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        state: "CT",
        timing: "good",
        current_price: 2.5,
        avg_price: 2.8,
        advice: "Good time to buy",
        data_points: 20,
      }),
    );
    const result = await getPropaneTiming("CT");
    expect(result.timing).toBe("good");
    expect(result.advice).toBe("Good time to buy");
  });
});
