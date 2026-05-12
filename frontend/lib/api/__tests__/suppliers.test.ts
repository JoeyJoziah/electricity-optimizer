import {
  getSuppliers,
  getSupplier,
  compareSuppliers,
  getRecommendation,
  initiateSwitch,
  getSwitchStatus,
  setUserSupplier,
  getUserSupplier,
  removeUserSupplier,
  linkSupplierAccount,
  getUserSupplierAccounts,
  unlinkSupplierAccount,
} from "@/lib/api/suppliers";
import { ApiClientError, _resetRedirectState } from "@/lib/api/client";
import "@testing-library/jest-dom";

// ---------------------------------------------------------------------------
// Setup - mock fetch (already globally mocked in jest.setup.js)
// ---------------------------------------------------------------------------

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>;
const originalLocation = window.location;

function mockJsonResponse(
  body: unknown,
  status = 200,
  statusText = "OK",
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
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

afterAll(() => {
  Object.defineProperty(window, "location", {
    writable: true,
    value: originalLocation,
  });
});

// ---------------------------------------------------------------------------
// getSuppliers
// ---------------------------------------------------------------------------

describe("getSuppliers", () => {
  it("calls correct endpoint", async () => {
    const responseData = {
      suppliers: [{ id: "1", name: "Eversource Energy", avgPricePerKwh: 0.25 }],
    };
    mockFetch.mockResolvedValue(mockJsonResponse(responseData));

    const result = await getSuppliers("us_ct");

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/suppliers");
    expect(result).toEqual(responseData);
  });

  it("passes region filter", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ suppliers: [] }));

    await getSuppliers("us_ny");

    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("region=us_ny");
  });
});

// ---------------------------------------------------------------------------
// getSupplier (by ID)
// ---------------------------------------------------------------------------

describe("getSupplierDetails", () => {
  it("fetches by ID", async () => {
    const supplier = {
      id: "supplier_001",
      name: "Eversource Energy",
      avgPricePerKwh: 0.25,
      rating: 4.5,
    };
    mockFetch.mockResolvedValue(mockJsonResponse(supplier));

    const result = await getSupplier("supplier_001");

    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/suppliers/supplier_001");
    expect(result).toEqual(supplier);
  });
});

// ---------------------------------------------------------------------------
// compareSuppliers
// ---------------------------------------------------------------------------

describe("compareSuppliers", () => {
  it("calls compare endpoint", async () => {
    const comparisonData = {
      comparisons: [
        { id: "1", name: "Eversource", estimatedAnnualCost: 1200 },
        { id: "2", name: "NextEra", estimatedAnnualCost: 1050 },
      ],
    };
    mockFetch.mockResolvedValue(mockJsonResponse(comparisonData));

    const result = await compareSuppliers(["1", "2"], 10500);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/suppliers/compare");

    // Verify it was a POST request with the correct body
    const calledOptions = mockFetch.mock.calls[0]![1] as RequestInit;
    expect(calledOptions.method).toBe("POST");
    expect(JSON.parse(calledOptions.body as string)).toEqual({
      supplierIds: ["1", "2"],
      annualUsage: 10500,
    });

    expect(result).toEqual(comparisonData);
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe("error handling", () => {
  it("handles 401 unauthorized", async () => {
    // Set pathname to auth page so 401 redirect is suppressed and error is thrown
    Object.defineProperty(window, "location", {
      writable: true,
      value: {
        ...originalLocation,
        pathname: "/auth/login",
        href: "http://localhost:3000/auth/login",
      },
    });

    mockFetch.mockResolvedValue(
      mockJsonResponse({ detail: "Not authenticated" }, 401, "Unauthorized"),
    );

    await expect(getSuppliers("us_ct")).rejects.toThrow(ApiClientError);

    try {
      await getSuppliers("us_ct");
    } catch (error) {
      const apiError = error as ApiClientError;
      expect(apiError.status).toBe(401);
    }
  });

  it("handles empty response", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ suppliers: [] }));

    const result = await getSuppliers("us_ct");

    expect(result).toEqual({ suppliers: [] });
    expect(result.suppliers).toHaveLength(0);
  });

  it("handles network error", async () => {
    mockFetch.mockRejectedValue(new TypeError("Failed to fetch"));

    // The client retries on network errors (TypeError), eventually throws
    await expect(getSuppliers("us_ct")).rejects.toThrow(TypeError);
  });

  it("request includes credentials for auth", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ suppliers: [] }));

    await getSuppliers("us_ct");

    const calledOptions = mockFetch.mock.calls[0]![1] as RequestInit;
    expect(calledOptions.credentials).toBe("include");
    expect(calledOptions.headers).toEqual(
      expect.objectContaining({ "Content-Type": "application/json" }),
    );
  });
});

// ---------------------------------------------------------------------------
// getSuppliers — annualUsage branch
// ---------------------------------------------------------------------------

describe("getSuppliers with annualUsage", () => {
  it("includes annual_usage param when provided", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ suppliers: [] }));
    await getSuppliers("us_ct", 12000);
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("annual_usage=12000");
  });
});

// ---------------------------------------------------------------------------
// getRecommendation
// ---------------------------------------------------------------------------

describe("getRecommendation", () => {
  it("POSTs to /suppliers/recommend with correct body", async () => {
    const mockRec = { recommendedSupplierId: "sup-2", estimatedSavings: 250 };
    mockFetch.mockResolvedValue(mockJsonResponse(mockRec));
    const result = await getRecommendation("sup-1", 10500, "us_ct");
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/suppliers/recommend");
    const body = JSON.parse(
      (mockFetch.mock.calls[0]![1] as RequestInit).body as string,
    );
    expect(body).toMatchObject({
      currentSupplierId: "sup-1",
      annualUsage: 10500,
      region: "us_ct",
    });
    expect(result).toEqual(mockRec);
  });
});

// ---------------------------------------------------------------------------
// initiateSwitch
// ---------------------------------------------------------------------------

describe("initiateSwitch", () => {
  it("POSTs to /suppliers/switch", async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ referenceNumber: "ref-42", status: "pending" }),
    );
    const result = await initiateSwitch({
      supplierId: "sup-2",
      currentSupplierId: "sup-1",
      annualUsage: 10500,
      region: "us_ct",
    });
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/suppliers/switch");
    expect((mockFetch.mock.calls[0]![1] as RequestInit).method).toBe("POST");
    expect(result.referenceNumber).toBe("ref-42");
  });
});

// ---------------------------------------------------------------------------
// getSwitchStatus
// ---------------------------------------------------------------------------

describe("getSwitchStatus", () => {
  it("GETs /suppliers/switch/{referenceNumber}", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ status: "completed" }));
    const result = await getSwitchStatus("ref-42");
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/suppliers/switch/ref-42");
    expect(result.status).toBe("completed");
  });
});

// ---------------------------------------------------------------------------
// setUserSupplier / getUserSupplier / removeUserSupplier
// ---------------------------------------------------------------------------

describe("setUserSupplier", () => {
  it("PUTs to /user/supplier with supplier_id", async () => {
    const mockResp = { supplier_id: "sup-3", supplier_name: "Spark Energy" };
    mockFetch.mockResolvedValue(mockJsonResponse(mockResp));
    const result = await setUserSupplier("sup-3");
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/user/supplier");
    expect((mockFetch.mock.calls[0]![1] as RequestInit).method).toBe("PUT");
    expect(result.supplier_id).toBe("sup-3");
  });
});

describe("getUserSupplier", () => {
  it("GETs /user/supplier", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ supplier: null }));
    const result = await getUserSupplier();
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/user/supplier");
    expect(result.supplier).toBeNull();
  });
});

describe("removeUserSupplier", () => {
  it("DELETEs /user/supplier", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ message: "removed" }));
    const result = await removeUserSupplier();
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/user/supplier");
    expect((mockFetch.mock.calls[0]![1] as RequestInit).method).toBe("DELETE");
    expect(result.message).toBe("removed");
  });
});

// ---------------------------------------------------------------------------
// linkSupplierAccount / getUserSupplierAccounts / unlinkSupplierAccount
// ---------------------------------------------------------------------------

describe("linkSupplierAccount", () => {
  it("POSTs to /user/supplier/link", async () => {
    const mockAccount = {
      supplier_id: "sup-3",
      supplier_name: "Spark",
      account_number_masked: "****1234",
    };
    mockFetch.mockResolvedValue(mockJsonResponse(mockAccount));
    const result = await linkSupplierAccount({
      supplier_id: "sup-3",
      account_number: "1234567890",
      consent_given: true,
    });
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/user/supplier/link");
    expect(result.supplier_id).toBe("sup-3");
  });
});

describe("getUserSupplierAccounts", () => {
  it("GETs /user/supplier/accounts", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ accounts: [] }));
    const result = await getUserSupplierAccounts();
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/user/supplier/accounts");
    expect(result.accounts).toEqual([]);
  });
});

describe("unlinkSupplierAccount", () => {
  it("DELETEs /user/supplier/accounts/{supplierId}", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ message: "unlinked" }));
    const result = await unlinkSupplierAccount("sup-3");
    const calledUrl = mockFetch.mock.calls[0]![0] as string;
    expect(calledUrl).toContain("/api/v1/user/supplier/accounts/sup-3");
    expect((mockFetch.mock.calls[0]![1] as RequestInit).method).toBe("DELETE");
    expect(result.message).toBe("unlinked");
  });
});
