import {
  getWaterRates,
  getWaterBenchmark,
  getWaterTips,
} from "@/lib/api/water";
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

describe("getWaterRates", () => {
  it("calls GET /rates/water without state filter", async () => {
    mockFetch.mockResolvedValue(mockJson({ rates: [] }));
    await getWaterRates();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/water");
    expect(url).not.toContain("state=");
  });

  it("passes state param when provided", async () => {
    mockFetch.mockResolvedValue(mockJson({ rates: [], count: 0 }));
    await getWaterRates("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("state=CT");
  });

  it("returns rates array", async () => {
    const rate = {
      id: "rate-1",
      municipality: "Hartford",
      state: "CT",
      rate_tiers: [{ limit_gallons: 1000, rate_per_gallon: 0.005 }],
      base_charge: 15.0,
      unit: "$/gallon",
      effective_date: "2026-01-01",
      source_url: null,
      updated_at: null,
    };
    mockFetch.mockResolvedValue(mockJson({ rates: [rate], count: 1 }));
    const result = await getWaterRates("CT");
    expect(result.rates).toHaveLength(1);
    expect(result.rates[0]!.municipality).toBe("Hartford");
  });
});

describe("getWaterBenchmark", () => {
  it("calls GET /rates/water/benchmark with state", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        state: "CT",
        municipalities: 5,
        usage_gallons: 3000,
        avg_monthly_cost: 45.0,
        min_monthly_cost: 30.0,
        max_monthly_cost: 65.0,
        rates: [],
      }),
    );
    await getWaterBenchmark("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/water/benchmark");
    expect(url).toContain("state=CT");
  });

  it("passes usage_gallons param when provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        state: "CT",
        municipalities: 5,
        usage_gallons: 5000,
        avg_monthly_cost: 62.5,
        min_monthly_cost: 40.0,
        max_monthly_cost: 90.0,
        rates: [],
      }),
    );
    await getWaterBenchmark("CT", 5000);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("usage_gallons=5000");
  });
});

describe("getWaterTips", () => {
  it("calls GET /rates/water/tips", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ tips: [], count: 0, estimated_annual_savings_gallons: 0 }),
    );
    await getWaterTips();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/water/tips");
  });

  it("returns tips array with estimated savings", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        tips: [
          {
            category: "bathroom",
            title: "Install low-flow showerhead",
            description: "Reduces flow from 2.5 to 1.8 gpm",
            estimated_savings_gallons: 2000,
            difficulty: "easy",
          },
        ],
        count: 1,
        estimated_annual_savings_gallons: 2000,
      }),
    );
    const result = await getWaterTips();
    expect(result.tips).toHaveLength(1);
    expect(result.tips[0]!.difficulty).toBe("easy");
    expect(result.estimated_annual_savings_gallons).toBe(2000);
  });
});
