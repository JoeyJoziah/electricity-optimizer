import {
  getNotifications,
  getNotificationCount,
  markNotificationRead,
  markAllRead,
} from "@/lib/api/notifications";
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
// getNotifications
// ---------------------------------------------------------------------------

describe("getNotifications", () => {
  it("calls GET /notifications", async () => {
    mockFetch.mockResolvedValue(mockJson({ notifications: [], total: 0 }));
    await getNotifications();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/notifications");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("returns notification list", async () => {
    const notif = {
      id: "notif-1",
      type: "rate_alert",
      title: "Price dropped",
      body: "Your region hit your threshold",
      created_at: "2026-05-01T00:00:00Z",
    };
    mockFetch.mockResolvedValue(mockJson({ notifications: [notif], total: 1 }));
    const result = await getNotifications();
    expect(result.total).toBe(1);
    expect(result.notifications[0]!.id).toBe("notif-1");
  });
});

// ---------------------------------------------------------------------------
// getNotificationCount
// ---------------------------------------------------------------------------

describe("getNotificationCount", () => {
  it("calls GET /notifications/count", async () => {
    mockFetch.mockResolvedValue(mockJson({ unread: 3 }));
    const result = await getNotificationCount();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/notifications/count");
    expect(result.unread).toBe(3);
  });

  it("returns zero when no unread", async () => {
    mockFetch.mockResolvedValue(mockJson({ unread: 0 }));
    const result = await getNotificationCount();
    expect(result.unread).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// markNotificationRead
// ---------------------------------------------------------------------------

describe("markNotificationRead", () => {
  it("calls PUT /notifications/{id}/read", async () => {
    mockFetch.mockResolvedValue(mockJson({ success: true }));
    const result = await markNotificationRead("notif-abc");
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/notifications/notif-abc/read");
    expect(call[1]?.method).toBe("PUT");
    expect(result.success).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// markAllRead — client-side batch
// ---------------------------------------------------------------------------

describe("markAllRead", () => {
  it("fetches unread list then marks each notification read", async () => {
    // First call: getNotifications
    mockFetch.mockResolvedValueOnce(
      mockJson({
        notifications: [
          {
            id: "n-1",
            type: "t",
            title: "T1",
            body: null,
            created_at: "2026-05-01T00:00:00Z",
          },
          {
            id: "n-2",
            type: "t",
            title: "T2",
            body: null,
            created_at: "2026-05-01T00:00:00Z",
          },
        ],
        total: 2,
      }),
    );
    // Subsequent calls: markNotificationRead for each
    mockFetch.mockResolvedValue(mockJson({ success: true }));

    await markAllRead();

    // 1 GET + 2 PUT
    expect(mockFetch).toHaveBeenCalledTimes(3);
    const urls = mockFetch.mock.calls.map((c) => c[0] as string);
    expect(urls[1]).toContain("/notifications/n-1/read");
    expect(urls[2]).toContain("/notifications/n-2/read");
  });

  it("does nothing when there are no notifications", async () => {
    mockFetch.mockResolvedValueOnce(mockJson({ notifications: [], total: 0 }));
    await markAllRead();
    // Only the GET call
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});
