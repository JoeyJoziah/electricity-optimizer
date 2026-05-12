import { recordAffiliateClick } from "@/lib/api/affiliate";
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

describe("recordAffiliateClick", () => {
  it("calls POST /affiliate/click", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        click_id: "clk-1",
        affiliate_url: "https://supplier.example.com",
      }),
    );
    await recordAffiliateClick({
      supplier_name: "GridCo",
      utility_type: "electricity",
      region: "US_CT",
      source_page: "/rates",
    });
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/affiliate/click");
    expect(call[1]?.method).toBe("POST");
  });

  it("returns click_id and affiliate_url", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ click_id: "clk-2", affiliate_url: "https://cheapenergy.com" }),
    );
    const result = await recordAffiliateClick({
      supplier_name: "CheapEnergy",
      utility_type: "gas",
      region: "US_NY",
      source_page: "/dashboard",
    });
    expect(result.click_id).toBe("clk-2");
    expect(result.affiliate_url).toBe("https://cheapenergy.com");
  });

  it("returns null affiliate_url when no affiliate link configured", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ click_id: "clk-3", affiliate_url: null }),
    );
    const result = await recordAffiliateClick({
      supplier_name: "NoAffiliateSupplier",
      utility_type: "electricity",
      region: "US_MA",
      source_page: "/compare",
    });
    expect(result.affiliate_url).toBeNull();
  });
});
