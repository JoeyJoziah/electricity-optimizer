import {
  detectCCA,
  compareCCARate,
  getCCAInfo,
  listCCAPrograms,
} from "@/lib/api/cca";
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

const _program = {
  id: "cca-1",
  state: "CA",
  municipality: "San Jose",
  program_name: "Silicon Valley Clean Energy",
  provider: "SVCE",
  generation_mix: null,
  rate_vs_default_pct: -5.0,
  opt_out_url: null,
  program_url: "https://svcleanenergy.org",
  status: "active",
};

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

describe("detectCCA", () => {
  it("calls GET /cca/detect", async () => {
    mockFetch.mockResolvedValue(mockJson({ in_cca: true, program: _program }));
    await detectCCA({ zip_code: "95101" });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/cca/detect");
    expect(url).toContain("zip_code=95101");
  });

  it("returns in_cca false when not in CCA territory", async () => {
    mockFetch.mockResolvedValue(mockJson({ in_cca: false, program: null }));
    const result = await detectCCA({ state: "TX" });
    expect(result.in_cca).toBe(false);
    expect(result.program).toBeNull();
  });
});

describe("compareCCARate", () => {
  it("calls GET /cca/compare/{id} with default_rate param", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        cca_id: "cca-1",
        program_name: "SVCE",
        provider: "SVCE",
        default_rate: 0.22,
        cca_rate: 0.19,
        rate_difference_pct: -13.6,
        savings_per_kwh: 0.03,
        estimated_monthly_savings: 24.0,
        is_cheaper: true,
      }),
    );
    await compareCCARate("cca-1", 0.22);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/cca/compare/cca-1");
    expect(url).toContain("default_rate=0.22");
  });

  it("returns is_cheaper true when CCA is cheaper", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        cca_id: "cca-1",
        program_name: "SVCE",
        provider: "SVCE",
        default_rate: 0.22,
        cca_rate: 0.19,
        rate_difference_pct: -13.6,
        savings_per_kwh: 0.03,
        estimated_monthly_savings: 24.0,
        is_cheaper: true,
      }),
    );
    const result = await compareCCARate("cca-1", 0.22);
    expect(result.is_cheaper).toBe(true);
    expect(result.estimated_monthly_savings).toBe(24.0);
  });
});

describe("getCCAInfo", () => {
  it("calls GET /cca/info/{id}", async () => {
    mockFetch.mockResolvedValue(mockJson(_program));
    await getCCAInfo("cca-1");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/cca/info/cca-1");
  });
});

describe("listCCAPrograms", () => {
  it("calls GET /cca/programs without state filter", async () => {
    mockFetch.mockResolvedValue(mockJson({ count: 0, programs: [] }));
    await listCCAPrograms();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/cca/programs");
  });

  it("passes state param when provided", async () => {
    mockFetch.mockResolvedValue(mockJson({ count: 1, programs: [_program] }));
    await listCCAPrograms("CA");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("state=CA");
  });
});
