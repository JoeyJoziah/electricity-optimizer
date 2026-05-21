import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseCommunityPosts = jest.fn();
const mockUseSettingsStore = jest.fn();

jest.mock("@/lib/hooks/useCommunity", () => ({
  useCommunityPosts: (...args: unknown[]) => mockUseCommunityPosts(...args),
}));

jest.mock("@/lib/store/settings", () => ({
  useSettingsStore: (selector: (s: { region: string }) => unknown) =>
    mockUseSettingsStore(selector),
}));

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ variant }: { variant: string }) => (
    <div data-testid={`skeleton-${variant}`} />
  ),
}));

jest.mock("@/components/community/VoteButton", () => ({
  VoteButton: ({ postId }: { postId: string }) => (
    <button data-testid={`vote-btn-${postId}`}>Vote</button>
  ),
}));

jest.mock("@/components/community/ReportButton", () => ({
  ReportButton: ({ postId }: { postId: string }) => (
    <button data-testid={`report-btn-${postId}`}>Report</button>
  ),
}));

import { PostList } from "@/components/community/PostList";

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

function setupStore(region = "us_ct") {
  mockUseSettingsStore.mockImplementation(
    (selector: (s: { region: string }) => unknown) => selector({ region }),
  );
}

function makePost(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    title: `Post title ${id}`,
    body: `Post body content for ${id}`,
    post_type: "tip",
    utility_type: "electricity",
    region: "us_ct",
    user_id: "user-1",
    upvote_count: 0,
    is_hidden: false,
    is_pending_moderation: false,
    rate_per_unit: null,
    rate_unit: null,
    supplier_name: null,
    created_at: "2026-05-12T10:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PostList", () => {
  beforeEach(() => {
    mockUseCommunityPosts.mockReset();
    mockUseSettingsStore.mockReset();
    setupStore();
  });

  it("shows loading skeletons when isLoading=true", () => {
    mockUseCommunityPosts.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("post-list-loading")).toBeInTheDocument();
  });

  it("shows error state when error is set", () => {
    mockUseCommunityPosts.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("post-list-error")).toBeInTheDocument();
    expect(
      screen.getByText(/unable to load community posts/i),
    ).toBeInTheDocument();
  });

  it("shows empty state when posts array is empty", () => {
    mockUseCommunityPosts.mockReturnValue({
      data: { posts: [], page: 1, pages: 0 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("post-list-empty")).toBeInTheDocument();
    expect(screen.getByText(/no posts yet/i)).toBeInTheDocument();
  });

  it("renders posts when data is available", () => {
    const posts = [makePost("p-1"), makePost("p-2")];
    mockUseCommunityPosts.mockReturnValue({
      data: { posts, page: 1, pages: 1 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("post-list")).toBeInTheDocument();
    expect(screen.getByTestId("post-p-1")).toBeInTheDocument();
    expect(screen.getByTestId("post-p-2")).toBeInTheDocument();
  });

  it("renders post title and body text", () => {
    const posts = [makePost("p-1")];
    mockUseCommunityPosts.mockReturnValue({
      data: { posts, page: 1, pages: 1 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.getByText("Post title p-1")).toBeInTheDocument();
    expect(screen.getByText("Post body content for p-1")).toBeInTheDocument();
  });

  it("renders VoteButton and ReportButton for each post", () => {
    const posts = [makePost("p-1")];
    mockUseCommunityPosts.mockReturnValue({
      data: { posts, page: 1, pages: 1 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("vote-btn-p-1")).toBeInTheDocument();
    expect(screen.getByTestId("report-btn-p-1")).toBeInTheDocument();
  });

  it("shows hidden post placeholder for non-author when is_hidden=true", () => {
    const posts = [
      makePost("p-hidden", { is_hidden: true, user_id: "other-user" }),
    ];
    mockUseCommunityPosts.mockReturnValue({
      data: { posts, page: 1, pages: 1 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" currentUserId="user-1" />, {
      wrapper: makeWrapper(),
    });
    expect(screen.getByTestId("post-p-hidden-hidden")).toBeInTheDocument();
    expect(screen.getByText("[Content under review]")).toBeInTheDocument();
  });

  it("shows pending moderation banner for author", () => {
    const posts = [
      makePost("p-pending", {
        is_pending_moderation: true,
        user_id: "user-1",
      }),
    ];
    mockUseCommunityPosts.mockReturnValue({
      data: { posts, page: 1, pages: 1 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" currentUserId="user-1" />, {
      wrapper: makeWrapper(),
    });
    expect(screen.getByTestId("post-p-pending-pending")).toBeInTheDocument();
    expect(
      screen.getByText(/your post is being reviewed/i),
    ).toBeInTheDocument();
  });

  it("shows flagged post with edit button for author", () => {
    const onEditPost = jest.fn();
    const post = makePost("p-flagged", {
      is_hidden: true,
      user_id: "user-1",
    });
    mockUseCommunityPosts.mockReturnValue({
      data: { posts: [post], page: 1, pages: 1 },
      isLoading: false,
      error: null,
    });
    render(
      <PostList
        utilityType="electricity"
        currentUserId="user-1"
        onEditPost={onEditPost}
      />,
      { wrapper: makeWrapper() },
    );
    expect(screen.getByTestId("post-p-flagged-flagged")).toBeInTheDocument();
    const editBtn = screen.getByTestId("post-p-flagged-edit-btn");
    fireEvent.click(editBtn);
    expect(onEditPost).toHaveBeenCalledWith(
      expect.objectContaining({ id: "p-flagged" }),
    );
  });

  it("shows rate info for rate_report posts", () => {
    const posts = [
      makePost("p-rate", {
        post_type: "rate_report",
        rate_per_unit: 0.15,
        rate_unit: "kWh",
        supplier_name: "GreenPower",
      }),
    ];
    mockUseCommunityPosts.mockReturnValue({
      data: { posts, page: 1, pages: 1 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.getByText(/Rate:.*GreenPower/)).toBeInTheDocument();
  });

  it("shows pagination when pages > 1", () => {
    const posts = [makePost("p-1")];
    mockUseCommunityPosts.mockReturnValue({
      data: { posts, page: 1, pages: 3 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("post-pagination")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
  });

  it("omits pagination when pages <= 1", () => {
    const posts = [makePost("p-1")];
    mockUseCommunityPosts.mockReturnValue({
      data: { posts, page: 1, pages: 1 },
      isLoading: false,
      error: null,
    });
    render(<PostList utilityType="electricity" />, { wrapper: makeWrapper() });
    expect(screen.queryByTestId("post-pagination")).not.toBeInTheDocument();
  });
});
