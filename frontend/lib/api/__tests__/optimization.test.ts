import {
  getOptimalSchedule,
  getOptimizationResult,
  saveAppliances,
  getAppliances,
  calculatePotentialSavings,
} from "@/lib/api/optimization";
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
// getOptimalSchedule
// ---------------------------------------------------------------------------

describe("getOptimalSchedule", () => {
  it("calls POST /optimization/schedule", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ schedules: [], totalSavings: 0, totalCost: 0 }),
    );
    await getOptimalSchedule({ appliances: [] });
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/optimization/schedule");
    expect(call[1]?.method).toBe("POST");
  });

  it("returns schedules and savings", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        schedules: [{ applianceId: "washer", startHour: 14, endHour: 16 }],
        totalSavings: 3.2,
        totalCost: 1.8,
      }),
    );
    const result = await getOptimalSchedule({ appliances: [] });
    expect(result.totalSavings).toBe(3.2);
    expect(result.schedules).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// getOptimizationResult
// ---------------------------------------------------------------------------

describe("getOptimizationResult", () => {
  it("calls GET /optimization/result with date and region params", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ date: "2026-05-12", region: "US_CT", savings: 2.5 }),
    );
    await getOptimizationResult("2026-05-12", "US_CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/optimization/result");
    expect(url).toContain("date=2026-05-12");
    expect(url).toContain("region=US_CT");
  });
});

// ---------------------------------------------------------------------------
// saveAppliances
// ---------------------------------------------------------------------------

describe("saveAppliances", () => {
  it("calls POST /optimization/appliances", async () => {
    mockFetch.mockResolvedValue(mockJson({ success: true }));
    const result = await saveAppliances([]);
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/optimization/appliances");
    expect(call[1]?.method).toBe("POST");
    expect(result.success).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// getAppliances
// ---------------------------------------------------------------------------

describe("getAppliances", () => {
  it("calls GET /optimization/appliances", async () => {
    mockFetch.mockResolvedValue(mockJson({ appliances: [] }));
    const result = await getAppliances();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/optimization/appliances");
    expect(result.appliances).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// calculatePotentialSavings
// ---------------------------------------------------------------------------

describe("calculatePotentialSavings", () => {
  it("calls POST /optimization/potential-savings", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        dailySavings: 0.45,
        weeklySavings: 3.15,
        monthlySavings: 13.5,
        annualSavings: 164.25,
      }),
    );
    const result = await calculatePotentialSavings([], "US_CT");
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/optimization/potential-savings");
    expect(call[1]?.method).toBe("POST");
    expect(result.annualSavings).toBe(164.25);
  });
});
