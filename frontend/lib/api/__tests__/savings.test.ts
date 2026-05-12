import { getCombinedSavings } from "@/lib/api/savings";
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
// getCombinedSavings
// ---------------------------------------------------------------------------

describe("getCombinedSavings", () => {
  it("calls GET /savings/combined", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        total_monthly_savings: 0,
        breakdown: [],
        savings_rank_pct: null,
      }),
    );
    await getCombinedSavings();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/savings/combined");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("returns total savings and breakdown", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        total_monthly_savings: 45.5,
        breakdown: [
          { utility_type: "electricity", monthly_savings: 30.0 },
          { utility_type: "gas", monthly_savings: 15.5 },
        ],
        savings_rank_pct: 82.5,
      }),
    );
    const result = await getCombinedSavings();
    expect(result.total_monthly_savings).toBe(45.5);
    expect(result.breakdown).toHaveLength(2);
    expect(result.savings_rank_pct).toBe(82.5);
  });

  it("returns null savings_rank_pct when not enough data", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        total_monthly_savings: 0,
        breakdown: [],
        savings_rank_pct: null,
      }),
    );
    const result = await getCombinedSavings();
    expect(result.savings_rank_pct).toBeNull();
  });
});
