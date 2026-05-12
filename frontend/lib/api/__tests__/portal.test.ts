import { createPortalConnection, triggerPortalScrape } from "@/lib/api/portal";
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

describe("createPortalConnection", () => {
  it("calls POST /connections/portal", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        connection_id: "conn-1",
        supplier_id: "sup-1",
        portal_username: "user@example.com",
        portal_login_url: "https://portal.example.com",
        portal_scrape_status: "pending",
        portal_last_scraped_at: null,
      }),
    );
    await createPortalConnection({
      supplier_id: "sup-1",
      portal_username: "user@example.com",
      portal_password: "s3cret",
      consent_given: true,
    });
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/connections/portal");
    expect(call[1]?.method).toBe("POST");
  });

  it("returns connection fields", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        connection_id: "conn-2",
        supplier_id: "sup-2",
        portal_username: "alice@example.com",
        portal_login_url: null,
        portal_scrape_status: "active",
        portal_last_scraped_at: "2026-05-01T12:00:00Z",
      }),
    );
    const result = await createPortalConnection({
      supplier_id: "sup-2",
      portal_username: "alice@example.com",
      portal_password: "pw",
      consent_given: true,
    });
    expect(result.connection_id).toBe("conn-2");
    expect(result.portal_scrape_status).toBe("active");
  });
});

describe("triggerPortalScrape", () => {
  it("calls POST /connections/portal/{id}/scrape", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        connection_id: "conn-1",
        status: "completed",
        rates_extracted: 3,
        error: null,
        scraped_at: "2026-05-12T10:00:00Z",
      }),
    );
    await triggerPortalScrape("conn-1");
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/connections/portal/conn-1/scrape");
    expect(call[1]?.method).toBe("POST");
  });

  it("returns rates_extracted count", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        connection_id: "conn-3",
        status: "completed",
        rates_extracted: 5,
        error: null,
        scraped_at: "2026-05-12T10:00:00Z",
      }),
    );
    const result = await triggerPortalScrape("conn-3");
    expect(result.rates_extracted).toBe(5);
    expect(result.error).toBeNull();
  });

  it("returns error when scrape fails", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        connection_id: "conn-4",
        status: "failed",
        rates_extracted: 0,
        error: "Login credentials invalid",
        scraped_at: null,
      }),
    );
    const result = await triggerPortalScrape("conn-4");
    expect(result.status).toBe("failed");
    expect(result.error).toBe("Login credentials invalid");
  });
});
