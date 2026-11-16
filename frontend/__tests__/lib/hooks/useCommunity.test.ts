import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockFetchPosts = jest.fn();
const mockCreatePost = jest.fn();
const mockToggleVote = jest.fn();
const mockReportPost = jest.fn();
const mockFetchCommunityStats = jest.fn();

jest.mock("@/lib/api/community", () => ({
  fetchPosts: (...args: unknown[]) => mockFetchPosts(...args),
  createPost: (...args: unknown[]) => mockCreatePost(...args),
  toggleVote: (...args: unknown[]) => mockToggleVote(...args),
  reportPost: (...args: unknown[]) => mockReportPost(...args),
  fetchCommunityStats: (...args: unknown[]) => mockFetchCommunityStats(...args),
}));

import {
  useCommunityPosts,
  useCreatePost,
  useToggleVote,
  useReportPost,
  useCommunityStats,
} from "@/lib/hooks/useCommunity";
import { waitFor } from "@testing-library/react";
import { ReactNode } from "react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestWrapper";
  return Wrapper;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useCommunityPosts", () => {
  it("is enabled when both region and utilityType are provided", () => {
    mockFetchPosts.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () => useCommunityPosts("us_ct", "electricity"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useCreatePost", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useCreatePost(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });

  it("calls createPost on mutate", async () => {
    mockCreatePost.mockResolvedValue({ id: "p-1" });
    const { result } = renderHook(() => useCreatePost(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate({
        region: "us_ct",
        utility_type: "electricity",
        title: "Test",
        body: "Test body",
        post_type: "general",
      });
    });
    expect(mockCreatePost).toHaveBeenCalledTimes(1);
  });
});

describe("useToggleVote", () => {
  it("calls toggleVote with postId", async () => {
    mockToggleVote.mockResolvedValue(undefined);
    const { result } = renderHook(() => useToggleVote(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate("post-99");
    });
    expect(mockToggleVote).toHaveBeenCalledWith("post-99");
  });
});

describe("useReportPost", () => {});

describe("useCommunityStats", () => {
  it("is enabled when region is provided", () => {
    mockFetchCommunityStats.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCommunityStats("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/hooks/useCommunity.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  function createWrapper() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    return {
      queryClient,
      wrapper: ({ children }: { children: ReactNode }) =>
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          children,
        ),
    };
  }

  const fakePosts = [{ id: "1", content: "hello" }];
  const fakeStats = { total_posts: 10, active_users: 5 };

  describe("useCommunityPosts", () => {
    beforeEach(() => jest.clearAllMocks());

    it("is disabled when region is undefined", () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(
        () => useCommunityPosts(undefined, "electricity"),
        { wrapper },
      );
      expect(result.current.fetchStatus).toBe("idle");
      expect(mockFetchPosts).not.toHaveBeenCalled();
    });

    it("is disabled when utilityType is undefined", () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useCommunityPosts("CT", undefined), {
        wrapper,
      });
      expect(result.current.fetchStatus).toBe("idle");
      expect(mockFetchPosts).not.toHaveBeenCalled();
    });

    it("is disabled when both region and utilityType are empty strings", () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useCommunityPosts("", ""), {
        wrapper,
      });
      expect(result.current.fetchStatus).toBe("idle");
    });

    it("fires the query when both region and utilityType are provided", async () => {
      mockFetchPosts.mockResolvedValue(fakePosts);
      const { wrapper } = createWrapper();
      const { result } = renderHook(
        () => useCommunityPosts("CT", "electricity"),
        { wrapper },
      );
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(mockFetchPosts).toHaveBeenCalledWith(
        "CT",
        "electricity",
        1,
        20,
        expect.any(AbortSignal),
      );
      expect(result.current.data).toEqual(fakePosts);
    });

    it("query key includes region, utilityType, and page", async () => {
      mockFetchPosts.mockResolvedValue(fakePosts);
      const { queryClient, wrapper } = createWrapper();
      renderHook(() => useCommunityPosts("NY", "gas", 2), { wrapper });
      await waitFor(() =>
        expect(
          queryClient.getQueryData(["community", "posts", "NY", "gas", 2]),
        ).toBeDefined(),
      );
    });
  });

  describe("useCommunityStats", () => {
    beforeEach(() => jest.clearAllMocks());

    it("is disabled when region is undefined", () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useCommunityStats(undefined), {
        wrapper,
      });
      expect(result.current.fetchStatus).toBe("idle");
      expect(mockFetchCommunityStats).not.toHaveBeenCalled();
    });

    it("fires the query when region is provided", async () => {
      mockFetchCommunityStats.mockResolvedValue(fakeStats);
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useCommunityStats("CT"), { wrapper });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(fakeStats);
    });

    it("query key includes region", async () => {
      mockFetchCommunityStats.mockResolvedValue(fakeStats);
      const { queryClient, wrapper } = createWrapper();
      renderHook(() => useCommunityStats("MA"), { wrapper });
      await waitFor(() =>
        expect(
          queryClient.getQueryData(["community", "stats", "MA"]),
        ).toBeDefined(),
      );
    });
  });

  describe("useCreatePost", () => {
    beforeEach(() => jest.clearAllMocks());

    it("calls createPost with the payload", async () => {
      mockCreatePost.mockResolvedValue({ id: "new-post" });
      mockFetchPosts.mockResolvedValue(fakePosts);
      mockFetchCommunityStats.mockResolvedValue(fakeStats);

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useCreatePost(), { wrapper });

      await act(async () => {
        result.current.mutate({
          title: "Test post",
          body: "test post",
          region: "CT",
          utility_type: "electricity",
          post_type: "tip",
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(mockCreatePost).toHaveBeenCalledWith({
        title: "Test post",
        body: "test post",
        region: "CT",
        utility_type: "electricity",
        post_type: "tip",
      });
    });
  });

  describe("useToggleVote", () => {
    beforeEach(() => jest.clearAllMocks());

    it("calls toggleVote with the postId", async () => {
      mockToggleVote.mockResolvedValue({ voted: true });
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useToggleVote(), { wrapper });

      await act(async () => {
        result.current.mutate("post-123");
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(mockToggleVote).toHaveBeenCalledWith("post-123");
    });
  });

  describe("useReportPost", () => {
    beforeEach(() => jest.clearAllMocks());

    it("calls reportPost with postId and reason", async () => {
      mockReportPost.mockResolvedValue({ reported: true });
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useReportPost(), { wrapper });

      await act(async () => {
        result.current.mutate({ postId: "post-abc", reason: "spam" });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(mockReportPost).toHaveBeenCalledWith("post-abc", "spam");
    });

    it("calls reportPost without reason when not provided", async () => {
      mockReportPost.mockResolvedValue({ reported: true });
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useReportPost(), { wrapper });

      await act(async () => {
        result.current.mutate({ postId: "post-abc" });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(mockReportPost).toHaveBeenCalledWith("post-abc", undefined);
    });
  });
}
