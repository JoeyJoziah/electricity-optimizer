import { exportRates, getExportTypes } from "@/lib/api/export";
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
// exportRates
// ---------------------------------------------------------------------------

describe("exportRates", () => {
  it("calls GET /export/rates with required params", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        format: "json",
        content_type: "application/json",
        data: [],
        count: 0,
        utility_type: "electricity",
        unit: "$/kWh",
        date_range: { start: "2026-01-01", end: "2026-05-12" },
      }),
    );
    await exportRates("electricity");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/export/rates");
    expect(url).toContain("utility_type=electricity");
    expect(url).toContain("format=json");
  });

  it("defaults to json format when not specified", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        format: "json",
        content_type: "application/json",
        data: [],
        count: 0,
        utility_type: "gas",
        unit: "$/therm",
        date_range: { start: "2026-01-01", end: "2026-05-12" },
      }),
    );
    await exportRates("gas");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("format=json");
  });

  it("passes csv format when specified", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        format: "csv",
        content_type: "text/csv",
        data: "utility_type,rate\n",
        count: 0,
        utility_type: "electricity",
        unit: "$/kWh",
        date_range: { start: "2026-01-01", end: "2026-05-12" },
      }),
    );
    await exportRates("electricity", "csv");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("format=csv");
  });

  it("passes optional state, start_date, end_date params", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        format: "json",
        content_type: "application/json",
        data: [],
        count: 0,
        utility_type: "electricity",
        unit: "$/kWh",
        date_range: { start: "2026-01-01", end: "2026-03-31" },
      }),
    );
    await exportRates("electricity", "json", "CT", "2026-01-01", "2026-03-31");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("state=CT");
    expect(url).toContain("start_date=2026-01-01");
    expect(url).toContain("end_date=2026-03-31");
  });

  it("omits optional params when not provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        format: "json",
        content_type: "application/json",
        data: [],
        count: 0,
        utility_type: "electricity",
        unit: "$/kWh",
        date_range: { start: "", end: "" },
      }),
    );
    await exportRates("electricity");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).not.toContain("state=");
    expect(url).not.toContain("start_date=");
    expect(url).not.toContain("end_date=");
  });
});

// ---------------------------------------------------------------------------
// getExportTypes
// ---------------------------------------------------------------------------

describe("getExportTypes", () => {
  it("calls GET /export/types", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        supported_types: ["electricity", "gas"],
        formats: ["json", "csv"],
        max_days: 365,
        max_rows: 10000,
      }),
    );
    await getExportTypes();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/export/types");
  });

  it("returns supported types and formats", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        supported_types: ["electricity", "gas", "heating_oil"],
        formats: ["json", "csv"],
        max_days: 365,
        max_rows: 10000,
      }),
    );
    const result = await getExportTypes();
    expect(result.supported_types).toContain("electricity");
    expect(result.formats).toContain("csv");
    expect(result.max_days).toBe(365);
  });
});
