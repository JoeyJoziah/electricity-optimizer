import { fetchPosts, createPost } from "@/lib/api/community";
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

const _postBase = {
  id: "post-1",
  user_id: "uid-1",
  region: "US_CT",
  utility_type: "electricity",
  post_type: "tip",
  title: "Save money with time-of-use rates",
  body: "Shift laundry to off-peak hours...",
  rate_per_unit: 0.12,
  rate_unit: "$/kWh",
  supplier_name: "GridCo",
  is_hidden: false,
  is_pending_moderation: false,
  hidden_reason: null,
  upvote_count: 15,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

describe("fetchPosts", () => {
  it("calls GET /community/posts with region and utility_type", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ posts: [], total: 0, page: 1, per_page: 20, pages: 0 }),
    );
    await fetchPosts("US_CT", "electricity");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/community/posts");
    expect(url).toContain("region=US_CT");
    expect(url).toContain("utility_type=electricity");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });

  it("passes page and per_page params", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ posts: [], total: 0, page: 2, per_page: 10, pages: 0 }),
    );
    await fetchPosts("US_CT", "electricity", 2, 10);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("page=2");
    expect(url).toContain("per_page=10");
  });

  it("returns posts array with pagination metadata", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        posts: [_postBase],
        total: 1,
        page: 1,
        per_page: 20,
        pages: 1,
      }),
    );
    const result = await fetchPosts("US_CT", "electricity");
    expect(result.posts).toHaveLength(1);
    expect(result.posts[0]!.id).toBe("post-1");
    expect(result.total).toBe(1);
  });
});

describe("createPost", () => {
  it("calls POST /community/posts", async () => {
    mockFetch.mockResolvedValue(mockJson(_postBase));
    await createPost({
      title: "Save money with time-of-use rates",
      body: "Shift laundry to off-peak hours...",
      utility_type: "electricity",
      region: "US_CT",
      post_type: "tip",
    });
    const call = mockFetch.mock.calls[0]!;
    expect(call[0] as string).toContain("/community/posts");
    expect(call[1]?.method).toBe("POST");
  });

  it("returns created post", async () => {
    mockFetch.mockResolvedValue(mockJson(_postBase));
    const result = await createPost({
      title: "Save money with time-of-use rates",
      body: "Shift laundry to off-peak hours...",
      utility_type: "electricity",
      region: "US_CT",
      post_type: "tip",
    });
    expect(result.id).toBe("post-1");
    expect(result.upvote_count).toBe(15);
  });
});
