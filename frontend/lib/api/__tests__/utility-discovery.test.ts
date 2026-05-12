import {
  discoverUtilities,
  getUtilityCompletion,
} from "@/lib/api/utility-discovery";
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

describe("discoverUtilities", () => {
  it("calls GET /utility-discovery/discover with state param", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ state: "CT", count: 3, utilities: [] }),
    );
    await discoverUtilities("CT");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/utility-discovery/discover");
    expect(url).toContain("state=CT");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("returns utilities array", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        state: "CT",
        count: 2,
        utilities: [
          {
            utility_type: "electricity",
            label: "Electricity",
            status: "deregulated",
            description: "CT electricity",
          },
          {
            utility_type: "gas",
            label: "Natural Gas",
            status: "deregulated",
            description: "CT gas",
          },
        ],
      }),
    );
    const result = await discoverUtilities("CT");
    expect(result.count).toBe(2);
    expect(result.utilities[0]!.status).toBe("deregulated");
  });
});

describe("getUtilityCompletion", () => {
  it("calls GET /utility-discovery/completion with state and tracked params", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        state: "CT",
        tracked: 2,
        available: 3,
        percent: 66.7,
        missing: [],
      }),
    );
    await getUtilityCompletion("CT", ["electricity", "gas"]);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/utility-discovery/completion");
    expect(url).toContain("state=CT");
    expect(url).toContain("tracked=electricity%2Cgas");
  });

  it("returns completion percentage", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        state: "CT",
        tracked: 3,
        available: 3,
        percent: 100.0,
        missing: [],
      }),
    );
    const result = await getUtilityCompletion("CT", [
      "electricity",
      "gas",
      "heating_oil",
    ]);
    expect(result.percent).toBe(100.0);
    expect(result.missing).toHaveLength(0);
  });
});
