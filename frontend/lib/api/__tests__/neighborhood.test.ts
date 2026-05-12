import { getNeighborhoodComparison } from "@/lib/api/neighborhood";
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

describe("getNeighborhoodComparison", () => {
  it("calls GET /neighborhood/compare with region and utility_type", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        utility_type: "electricity",
        user_count: 120,
        percentile: 75,
        user_rate: 0.18,
        cheapest_supplier: "GridCo",
        cheapest_rate: 0.14,
        avg_rate: 0.17,
        potential_savings: 20.0,
      }),
    );
    await getNeighborhoodComparison("US_CT", "electricity");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/neighborhood/compare");
    expect(url).toContain("region=US_CT");
    expect(url).toContain("utility_type=electricity");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("returns comparison fields", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_CT",
        utility_type: "electricity",
        user_count: 50,
        percentile: 40,
        user_rate: 0.2,
        cheapest_supplier: "CheapCo",
        cheapest_rate: 0.12,
        avg_rate: 0.17,
        potential_savings: 38.4,
      }),
    );
    const result = await getNeighborhoodComparison("US_CT", "electricity");
    expect(result.percentile).toBe(40);
    expect(result.cheapest_supplier).toBe("CheapCo");
    expect(result.potential_savings).toBe(38.4);
  });

  it("handles null fields when no data available", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        region: "US_MT",
        utility_type: "gas",
        user_count: 0,
        percentile: null,
        user_rate: null,
        cheapest_supplier: null,
        cheapest_rate: null,
        avg_rate: null,
        potential_savings: null,
      }),
    );
    const result = await getNeighborhoodComparison("US_MT", "gas");
    expect(result.percentile).toBeNull();
    expect(result.user_count).toBe(0);
  });
});
