import {
  getGasRates,
  getGasHistory,
  getGasStats,
  getDeregulatedGasStates,
  compareGasSuppliers,
} from "@/lib/api/gas-rates";
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

describe("getGasRates", () => {
  it("calls GET /rates/natural-gas/ with region", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        utility_type: "natural_gas",
        unit: "$/therm",
        is_deregulated: true,
        count: 0,
        prices: [],
      }),
    );
    await getGasRates({ region: "US_CT" });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/natural-gas/");
    expect(url).toContain("region=US_CT");
  });

  it("passes optional limit param", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        utility_type: "natural_gas",
        unit: "$/therm",
        is_deregulated: true,
        count: 0,
        prices: [],
      }),
    );
    await getGasRates({ region: "US_CT", limit: 5 });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("limit=5");
  });
});

describe("getGasHistory", () => {
  it("calls GET /rates/natural-gas/history", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        utility_type: "natural_gas",
        period_days: 30,
        count: 0,
        prices: [],
      }),
    );
    await getGasHistory({ region: "US_CT" });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/natural-gas/history");
    expect(url).toContain("region=US_CT");
  });

  it("passes optional days param", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        utility_type: "natural_gas",
        period_days: 60,
        count: 0,
        prices: [],
      }),
    );
    await getGasHistory({ region: "US_CT", days: 60 });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("days=60");
  });
});

describe("getGasStats", () => {
  it("calls GET /rates/natural-gas/stats", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        utility_type: "natural_gas",
        unit: "$/therm",
        avg_price: "1.50",
        min_price: "1.20",
        max_price: "1.80",
        count: 10,
      }),
    );
    await getGasStats({ region: "US_CT" });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/natural-gas/stats");
  });
});

describe("getDeregulatedGasStates", () => {
  it("calls GET /rates/natural-gas/deregulated-states", async () => {
    mockFetch.mockResolvedValue(mockJson({ count: 2, states: [] }));
    await getDeregulatedGasStates();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/natural-gas/deregulated-states");
  });
});

describe("compareGasSuppliers", () => {
  it("calls GET /rates/natural-gas/compare with region", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        is_deregulated: true,
        suppliers: [],
        cheapest: null,
      }),
    );
    await compareGasSuppliers("US_CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/rates/natural-gas/compare");
    expect(url).toContain("region=US_CT");
  });

  it("returns cheapest supplier when available", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        is_deregulated: true,
        unit: "$/therm",
        suppliers: [
          {
            supplier: "GasCo",
            price: "1.20",
            timestamp: "2026-05-01T00:00:00Z",
            source: "market",
          },
        ],
        cheapest: "GasCo",
      }),
    );
    const result = await compareGasSuppliers("US_CT");
    expect(result.cheapest).toBe("GasCo");
  });
});
