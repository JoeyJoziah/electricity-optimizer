import { getAutoSwitcherActivity } from "@/lib/api/auto-switcher";
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

describe("getAutoSwitcherActivity", () => {
  it("calls GET /agent-switcher/activity", async () => {
    mockFetch.mockResolvedValue(mockJson([]));
    await getAutoSwitcherActivity();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/activity");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("passes limit param", async () => {
    mockFetch.mockResolvedValue(mockJson([]));
    await getAutoSwitcherActivity(5);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("limit=5");
  });

  it("defaults to limit=10", async () => {
    mockFetch.mockResolvedValue(mockJson([]));
    await getAutoSwitcherActivity();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("limit=10");
  });

  it("returns activity array", async () => {
    const activity = [
      {
        id: "act-1",
        decision: "switch",
        executed: true,
        created_at: "2026-05-12T00:00:00Z",
        rate_plan_id: "plan-abc",
        savings_estimate: 22.5,
        region: "US_CT",
      },
    ];
    mockFetch.mockResolvedValue(mockJson(activity));
    const result = await getAutoSwitcherActivity();
    expect(result).toHaveLength(1);
    expect(result[0]!.decision).toBe("switch");
  });

  it("returns empty array when no activity", async () => {
    mockFetch.mockResolvedValue(mockJson([]));
    const result = await getAutoSwitcherActivity();
    expect(result).toEqual([]);
  });
});
