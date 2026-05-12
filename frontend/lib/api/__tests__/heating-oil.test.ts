import {
  getHeatingOilPrices,
  getHeatingOilHistory,
  getHeatingOilDealers,
  getHeatingOilComparison,
} from "@/lib/api/heating-oil";
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

describe("getHeatingOilPrices", () => {
  it("calls GET /rates/heating-oil without state filter", async () => {
    mockFetch.mockResolvedValue(mockJson({ prices: [], tracked_states: [] }));
    await getHeatingOilPrices();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/heating-oil");
    expect(url).not.toContain("state=");
  });

  it("passes state param when provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ prices: [], tracked_states: ["CT"] }),
    );
    await getHeatingOilPrices("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("state=CT");
  });
});

describe("getHeatingOilHistory", () => {
  it("calls GET /rates/heating-oil/history with state", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "CT", weeks: 4, history: [], comparison: null }),
    );
    await getHeatingOilHistory("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/heating-oil/history");
    expect(url).toContain("state=CT");
  });

  it("passes weeks param when provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "CT", weeks: 8, history: [], comparison: null }),
    );
    await getHeatingOilHistory("CT", 8);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("weeks=8");
  });
});

describe("getHeatingOilDealers", () => {
  it("calls GET /rates/heating-oil/dealers with state", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "CT", count: 0, dealers: [] }),
    );
    await getHeatingOilDealers("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/heating-oil/dealers");
    expect(url).toContain("state=CT");
  });

  it("passes limit param when provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "CT", count: 0, dealers: [] }),
    );
    await getHeatingOilDealers("CT", 5);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("limit=5");
  });
});

describe("getHeatingOilComparison", () => {
  it("calls GET /rates/heating-oil/compare with state", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        state: "CT",
        price_per_gallon: 3.85,
        national_avg: 3.6,
        difference_pct: 6.9,
        estimated_monthly_cost: 231.0,
        estimated_annual_cost: 2772.0,
      }),
    );
    await getHeatingOilComparison("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/heating-oil/compare");
    expect(url).toContain("state=CT");
  });
});
