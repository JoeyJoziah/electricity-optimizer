import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockMutate = jest.fn();
const mockUseToggleVote = jest.fn();

jest.mock("@/lib/hooks/useCommunity", () => ({
  useToggleVote: () => mockUseToggleVote(),
}));

import { VoteButton } from "@/components/community/VoteButton";

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

function setup(overrides: Record<string, unknown> = {}) {
  mockUseToggleVote.mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("VoteButton", () => {
  beforeEach(() => {
    mockMutate.mockReset();
    mockUseToggleVote.mockReset();
  });

  it("renders button with testid vote-btn-{postId}", () => {
    setup();
    render(<VoteButton postId="post-1" count={5} />, {
      wrapper: makeWrapper(),
    });
    expect(screen.getByTestId("vote-btn-post-1")).toBeInTheDocument();
  });

  it("shows initial vote count", () => {
    setup();
    render(<VoteButton postId="post-1" count={42} />, {
      wrapper: makeWrapper(),
    });
    expect(screen.getByTestId("vote-count-post-1")).toHaveTextContent("42");
  });

  it("increments count optimistically on first click", () => {
    setup();
    render(<VoteButton postId="post-1" count={10} />, {
      wrapper: makeWrapper(),
    });
    fireEvent.click(screen.getByTestId("vote-btn-post-1"));
    expect(screen.getByTestId("vote-count-post-1")).toHaveTextContent("11");
  });

  it("decrements count optimistically on second click (un-vote)", () => {
    setup();
    render(<VoteButton postId="post-1" count={10} />, {
      wrapper: makeWrapper(),
    });
    fireEvent.click(screen.getByTestId("vote-btn-post-1"));
    fireEvent.click(screen.getByTestId("vote-btn-post-1"));
    expect(screen.getByTestId("vote-count-post-1")).toHaveTextContent("10");
  });

  it("calls mutation.mutate with postId when clicked", () => {
    setup();
    render(<VoteButton postId="post-42" count={0} />, {
      wrapper: makeWrapper(),
    });
    fireEvent.click(screen.getByTestId("vote-btn-post-42"));
    expect(mockMutate).toHaveBeenCalledWith("post-42", expect.any(Object));
  });

  it("disables button when isPending=true", () => {
    setup({ isPending: true });
    render(<VoteButton postId="post-1" count={0} />, {
      wrapper: makeWrapper(),
    });
    expect(screen.getByTestId("vote-btn-post-1")).toBeDisabled();
  });

  it("updates count from onSuccess response", async () => {
    mockUseToggleVote.mockReturnValue({
      isPending: false,
      mutate: jest.fn().mockImplementation((_id, opts) => {
        opts.onSuccess({ voted: true, upvote_count: 99 });
      }),
    });

    render(<VoteButton postId="post-1" count={5} />, {
      wrapper: makeWrapper(),
    });
    fireEvent.click(screen.getByTestId("vote-btn-post-1"));
    await waitFor(() =>
      expect(screen.getByTestId("vote-count-post-1")).toHaveTextContent("99"),
    );
  });

  it("reverts count on onError", async () => {
    mockUseToggleVote.mockReturnValue({
      isPending: false,
      mutate: jest.fn().mockImplementation((_id, opts) => {
        opts.onError();
      }),
    });

    render(<VoteButton postId="post-1" count={5} />, {
      wrapper: makeWrapper(),
    });
    fireEvent.click(screen.getByTestId("vote-btn-post-1"));
    // Should revert to original count 5 after error
    await waitFor(() =>
      expect(screen.getByTestId("vote-count-post-1")).toHaveTextContent("5"),
    );
  });

  it("never shows negative count on decrement below zero", () => {
    setup();
    render(<VoteButton postId="post-1" count={0} />, {
      wrapper: makeWrapper(),
    });
    // First click votes (goes to 1), second click un-votes (back to 0)
    fireEvent.click(screen.getByTestId("vote-btn-post-1"));
    fireEvent.click(screen.getByTestId("vote-btn-post-1"));
    const count = parseInt(
      screen.getByTestId("vote-count-post-1").textContent || "0",
      10,
    );
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
