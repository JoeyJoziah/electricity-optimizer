import {
  generateMessageId,
  submitAgentTask,
  getTaskResult,
  getAgentUsage,
  queryAgent,
} from "@/lib/api/agent";

const mockApiClientGet = jest.fn();
const mockApiClientPost = jest.fn();
const mockHandle401Redirect = jest.fn(() => false);
const mockFetch = jest.fn();

jest.mock("@/lib/api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => mockApiClientGet(...a),
    post: (...a: unknown[]) => mockApiClientPost(...a),
  },
  handle401Redirect: () => mockHandle401Redirect(),
}));
jest.mock("@/lib/config/env", () => ({ API_URL: "https://api.test.invalid" }));

global.fetch = mockFetch as typeof fetch;

beforeEach(() => {
  mockApiClientGet.mockReset();
  mockApiClientPost.mockReset();
  mockHandle401Redirect.mockReset().mockReturnValue(false);
  mockFetch.mockReset();
});

// ---------------------------------------------------------------------------
// generateMessageId
// ---------------------------------------------------------------------------
describe("generateMessageId", () => {
  it("returns a string starting with msg-", () => {
    expect(generateMessageId()).toMatch(/^msg-/);
  });

  it("returns unique IDs on each call", () => {
    const id1 = generateMessageId();
    const id2 = generateMessageId();
    expect(id1).not.toBe(id2);
  });
});

// ---------------------------------------------------------------------------
// submitAgentTask
// ---------------------------------------------------------------------------
describe("submitAgentTask", () => {
  it("calls apiClient.post with the prompt and context", async () => {
    mockApiClientPost.mockResolvedValueOnce({ job_id: "job-42" });
    const result = await submitAgentTask("what is my rate?", { region: "CT" });
    expect(mockApiClientPost).toHaveBeenCalledWith("/agent/task", {
      prompt: "what is my rate?",
      context: { region: "CT" },
    });
    expect(result).toEqual({ job_id: "job-42" });
  });
});

// ---------------------------------------------------------------------------
// getTaskResult
// ---------------------------------------------------------------------------
describe("getTaskResult", () => {
  it("calls apiClient.get for the job ID", async () => {
    mockApiClientGet.mockResolvedValueOnce({
      status: "completed",
      result: "done",
    });
    const result = await getTaskResult("job-99");
    expect(mockApiClientGet).toHaveBeenCalledWith(
      "/agent/task/job-99",
      undefined,
      { signal: undefined },
    );
    expect(result.status).toBe("completed");
  });
});

// ---------------------------------------------------------------------------
// getAgentUsage
// ---------------------------------------------------------------------------
describe("getAgentUsage", () => {
  it("calls apiClient.get for usage endpoint", async () => {
    mockApiClientGet.mockResolvedValueOnce({
      used: 3,
      limit: 20,
      remaining: 17,
      tier: "pro",
    });
    const result = await getAgentUsage();
    expect(mockApiClientGet).toHaveBeenCalledWith("/agent/usage", undefined, {
      signal: undefined,
    });
    expect(result.remaining).toBe(17);
  });
});

// ---------------------------------------------------------------------------
// queryAgent (SSE streaming)
// ---------------------------------------------------------------------------
describe("queryAgent", () => {
  it("yields an error message on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Server error" }),
    });
    const messages = [];
    for await (const msg of queryAgent("test prompt")) {
      messages.push(msg);
    }
    expect(messages).toHaveLength(1);
    expect(messages[0].role).toBe("error");
    expect(messages[0].content).toBe("Server error");
  });

  it("returns immediately after 401 when handle401Redirect returns true", async () => {
    mockHandle401Redirect.mockReturnValue(true);
    mockFetch.mockResolvedValueOnce({ ok: false, status: 401 });
    const messages = [];
    for await (const msg of queryAgent("test")) {
      messages.push(msg);
    }
    expect(messages).toHaveLength(0);
  });

  it("yields error when response body is null (no reader)", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, body: null });
    const messages = [];
    for await (const msg of queryAgent("test")) {
      messages.push(msg);
    }
    expect(messages[0].role).toBe("error");
    expect(messages[0].content).toMatch(/streaming not supported/i);
  });
});
