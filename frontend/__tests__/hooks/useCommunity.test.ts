import { renderHook, waitFor, act } from "@testing-library/react";
import React, { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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
    const { result } = renderHook(() => useCommunityPosts("", ""), { wrapper });
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
        region: "CT",
        utility_type: "electricity",
        content: "test post",
      } as Parameters<typeof result.current.mutate>[0]);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCreatePost).toHaveBeenCalledWith({
      region: "CT",
      utility_type: "electricity",
      content: "test post",
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
