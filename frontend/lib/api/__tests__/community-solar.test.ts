import {
  getCommunitySolarPrograms,
  getCommunitySolarSavings,
  getCommunitySolarProgram,
  getCommunitySolarStates,
} from "@/lib/api/community-solar";
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
  id: "prog-1",
  state: "NY",
  program_name: "NY Community Solar",
  provider: "Nexamp",
  savings_percent: "10.00",
  capacity_kw: "5000.00",
  spots_available: 100,
  enrollment_url: "https://example.com",
  enrollment_status: "open",
  description: "Save on your bill",
  min_bill_amount: "50.00",
  contract_months: 12,
  updated_at: "2026-03-10T00:00:00Z",
};

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

describe("getCommunitySolarPrograms", () => {
  it("calls GET /community-solar/programs with state", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "NY", count: 1, programs: [_program] }),
    );
    await getCommunitySolarPrograms({ state: "NY" });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/community-solar/programs");
    expect(url).toContain("state=NY");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("passes enrollment_status when provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "NY", count: 0, programs: [] }),
    );
    await getCommunitySolarPrograms({ state: "NY", enrollment_status: "open" });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("enrollment_status=open");
  });

  it("passes limit when provided", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "NY", count: 0, programs: [] }),
    );
    await getCommunitySolarPrograms({ state: "NY", limit: 5 });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("limit=5");
  });

  it("returns programs array", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "NY", count: 1, programs: [_program] }),
    );
    const result = await getCommunitySolarPrograms({ state: "NY" });
    expect(result.programs).toHaveLength(1);
    expect(result.programs[0]!.enrollment_status).toBe("open");
  });
});

describe("getCommunitySolarSavings", () => {
  it("calls POST or GET /community-solar/savings", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        current_monthly_bill: "150.00",
        savings_percent: "10",
        monthly_savings: "15.00",
        annual_savings: "180.00",
        five_year_savings: "900.00",
        new_monthly_bill: "135.00",
      }),
    );
    await getCommunitySolarSavings({
      monthly_bill: "150.00",
      savings_percent: "10",
    });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("community-solar");
  });

  it("returns savings fields", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        current_monthly_bill: "200.00",
        savings_percent: "15",
        monthly_savings: "30.00",
        annual_savings: "360.00",
        five_year_savings: "1800.00",
        new_monthly_bill: "170.00",
      }),
    );
    const result = await getCommunitySolarSavings({
      monthly_bill: "200.00",
      savings_percent: "15",
    });
    expect(result.monthly_savings).toBe("30.00");
    expect(result.five_year_savings).toBe("1800.00");
  });
});

describe("getCommunitySolarProgram", () => {
  it("calls GET /community-solar/programs/{id}", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ ..._program, created_at: "2026-01-01T00:00:00Z" }),
    );
    await getCommunitySolarProgram("prog-1");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("prog-1");
  });
});

describe("getCommunitySolarStates", () => {
  it("calls GET /community-solar/states", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        total_states: 2,
        states: [{ state: "NY", program_count: 3 }],
      }),
    );
    await getCommunitySolarStates();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("community-solar");
  });

  it("returns states list", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        total_states: 1,
        states: [{ state: "MA", program_count: 2 }],
      }),
    );
    const result = await getCommunitySolarStates();
    expect(result.total_states).toBe(1);
    expect(result.states[0]!.state).toBe("MA");
  });
});
