import { getOptimizationReport } from "@/lib/api/reports";
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

const _reportBase = {
  state: "CT",
  generated_at: "2026-05-12T00:00:00Z",
  utilities: [],
  total_monthly_spend: 150.0,
  total_annual_spend: 1800.0,
  savings_opportunities: [],
  total_potential_monthly_savings: 25.0,
  total_potential_annual_savings: 300.0,
  utility_count: 2,
};

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

describe("getOptimizationReport", () => {
  it("calls GET /reports/optimization with state param", async () => {
    mockFetch.mockResolvedValue(mockJson(_reportBase));
    await getOptimizationReport("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/reports/optimization");
    expect(url).toContain("state=CT");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("returns report fields", async () => {
    mockFetch.mockResolvedValue(mockJson(_reportBase));
    const result = await getOptimizationReport("CT");
    expect(result.state).toBe("CT");
    expect(result.total_monthly_spend).toBe(150.0);
    expect(result.total_potential_annual_savings).toBe(300.0);
    expect(result.utility_count).toBe(2);
  });

  it("returns utilities and savings_opportunities arrays", async () => {
    const report = {
      ..._reportBase,
      utilities: [
        {
          utility_type: "electricity",
          unit: "$/kWh",
          current_rate: 0.18,
          monthly_consumption: 800,
          consumption_unit: "kWh",
          monthly_cost: 144.0,
          savings: null,
        },
      ],
      savings_opportunities: [
        {
          utility_type: "electricity",
          action: "Switch supplier",
          monthly_savings: 20.0,
          annual_savings: 240.0,
          difficulty: "easy",
        },
      ],
    };
    mockFetch.mockResolvedValue(mockJson(report));
    const result = await getOptimizationReport("CT");
    expect(result.utilities).toHaveLength(1);
    expect(result.savings_opportunities[0]!.difficulty).toBe("easy");
  });
});
