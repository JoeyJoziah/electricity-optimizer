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
  it("is disabled when region is undefined", () => {
    const { result } = renderHook(
      () => useCommunityPosts(undefined, "electricity"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when utilityType is undefined", () => {
    const { result } = renderHook(() => useCommunityPosts("us_ct", undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

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

describe("useReportPost", () => {
  it("calls reportPost with postId and reason", async () => {
    mockReportPost.mockResolvedValue(undefined);
    const { result } = renderHook(() => useReportPost(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate({ postId: "post-7", reason: "spam" });
    });
    expect(mockReportPost).toHaveBeenCalledWith("post-7", "spam");
  });
});

describe("useCommunityStats", () => {
  it("is disabled when region is undefined", () => {
    const { result } = renderHook(() => useCommunityStats(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when region is provided", () => {
    mockFetchCommunityStats.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCommunityStats("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
