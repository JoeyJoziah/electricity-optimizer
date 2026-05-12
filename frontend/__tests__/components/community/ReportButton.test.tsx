import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockMutate = jest.fn();
const mockUseReportPost = jest.fn();

jest.mock("@/lib/hooks/useCommunity", () => ({
  useReportPost: () => mockUseReportPost(),
}));

import { ReportButton } from "@/components/community/ReportButton";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

function setup(overrides: Record<string, unknown> = {}) {
  mockUseReportPost.mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ReportButton", () => {
  beforeEach(() => {
    mockMutate.mockReset();
    mockUseReportPost.mockReset();
  });

  it("renders initial Report button", () => {
    setup();
    render(<ReportButton postId="post-1" />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("report-btn-post-1")).toBeInTheDocument();
    expect(screen.getByTestId("report-btn-post-1")).toHaveTextContent("Report");
  });

  it("shows confirmation UI after clicking Report", () => {
    setup();
    render(<ReportButton postId="post-1" />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("report-btn-post-1"));
    expect(screen.getByTestId("report-confirm-post-1")).toBeInTheDocument();
    expect(screen.getByText(/report this post\?/i)).toBeInTheDocument();
    expect(screen.getByTestId("report-yes-post-1")).toBeInTheDocument();
  });

  it("hides initial Report button after clicking it", () => {
    setup();
    render(<ReportButton postId="post-1" />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("report-btn-post-1"));
    expect(screen.queryByTestId("report-btn-post-1")).not.toBeInTheDocument();
  });

  it("calls mutate with postId when Yes is clicked", () => {
    setup();
    render(<ReportButton postId="post-42" />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("report-btn-post-42"));
    fireEvent.click(screen.getByTestId("report-yes-post-42"));
    expect(mockMutate).toHaveBeenCalledWith(
      { postId: "post-42" },
      expect.any(Object),
    );
  });

  it("returns to initial state when No is clicked", () => {
    setup();
    render(<ReportButton postId="post-1" />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("report-btn-post-1"));
    fireEvent.click(screen.getByRole("button", { name: /^No$/i }));
    expect(screen.getByTestId("report-btn-post-1")).toBeInTheDocument();
    expect(
      screen.queryByTestId("report-confirm-post-1"),
    ).not.toBeInTheDocument();
  });

  it("disables Yes button while mutation is pending", () => {
    setup({ isPending: true });
    render(<ReportButton postId="post-1" />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("report-btn-post-1"));
    expect(screen.getByTestId("report-yes-post-1")).toBeDisabled();
  });

  it("hides confirm UI on successful mutation via onSuccess callback", async () => {
    mockUseReportPost.mockReturnValue({
      isPending: false,
      mutate: jest.fn().mockImplementation((_vars, opts) => {
        opts.onSuccess();
      }),
    });
    render(<ReportButton postId="post-1" />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("report-btn-post-1"));
    fireEvent.click(screen.getByTestId("report-yes-post-1"));
    await waitFor(() =>
      expect(
        screen.queryByTestId("report-confirm-post-1"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("report-btn-post-1")).toBeInTheDocument();
  });
});
