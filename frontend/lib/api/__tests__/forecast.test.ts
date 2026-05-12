import { getForecast, getForecastTypes } from "@/lib/api/forecast";
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

const _forecastBase = {
  utility_type: "electricity",
  state: "CT",
  unit: "$/kWh",
  current_rate: 0.18,
  forecasted_rate: 0.19,
  horizon_days: 30,
  trend: "increasing",
  percent_change: 5.6,
  confidence: 0.82,
  model: "ensemble",
  data_points: 180,
  r_squared: 0.91,
  generated_at: "2026-05-12T00:00:00Z",
};

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

// ---------------------------------------------------------------------------
// getForecast
// ---------------------------------------------------------------------------

describe("getForecast", () => {
  it("calls GET /forecast/{utilityType}", async () => {
    mockFetch.mockResolvedValue(mockJson(_forecastBase));
    await getForecast("electricity");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/forecast/electricity");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("passes state and horizon_days when provided", async () => {
    mockFetch.mockResolvedValue(mockJson(_forecastBase));
    await getForecast("electricity", "CT", 60);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("state=CT");
    expect(url).toContain("horizon_days=60");
  });

  it("omits state and horizon_days when not provided", async () => {
    mockFetch.mockResolvedValue(mockJson(_forecastBase));
    await getForecast("gas");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).not.toContain("state=");
    expect(url).not.toContain("horizon_days=");
  });

  it("returns forecast fields", async () => {
    mockFetch.mockResolvedValue(mockJson(_forecastBase));
    const result = await getForecast("electricity", "CT");
    expect(result.trend).toBe("increasing");
    expect(result.confidence).toBe(0.82);
    expect(result.forecasted_rate).toBe(0.19);
  });
});

// ---------------------------------------------------------------------------
// getForecastTypes
// ---------------------------------------------------------------------------

describe("getForecastTypes", () => {
  it("calls GET /forecast", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        supported_types: ["electricity", "gas", "heating_oil"],
        description: "Available forecast utility types",
      }),
    );
    await getForecastTypes();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toMatch(/\/forecast$/);
  });

  it("returns supported types list", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        supported_types: ["electricity", "gas"],
        description: "desc",
      }),
    );
    const result = await getForecastTypes();
    expect(result.supported_types).toContain("electricity");
    expect(result.supported_types).toContain("gas");
  });
});
