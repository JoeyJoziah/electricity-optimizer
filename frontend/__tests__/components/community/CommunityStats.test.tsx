import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseCommunityStats = jest.fn();
const mockUseSettingsStore = jest.fn();

jest.mock("@/lib/hooks/useCommunity", () => ({
  useCommunityStats: (...args: unknown[]) => mockUseCommunityStats(...args),
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

import { CommunityStats } from "@/components/community/CommunityStats";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setup(statsOverrides: Record<string, unknown> = {}) {
  mockUseSettingsStore.mockImplementation(
    (selector: (s: { region: string }) => unknown) =>
      selector({ region: "us_ct" }),
  );
  mockUseCommunityStats.mockReturnValue({
    data: null,
    isLoading: false,
    error: null,
    ...statsOverrides,
  });
}

const _stats = {
  user_count: 142,
  avg_savings_pct: 18.5,
  post_count: 87,
  since: "2025-01-01T00:00:00Z",
  top_tip: {
    id: "tip-1",
    title: "Switch to off-peak charging for EVs",
  },
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CommunityStats", () => {
  beforeEach(() => {
    mockUseCommunityStats.mockReset();
    mockUseSettingsStore.mockReset();
  });

  it("renders loading skeleton when isLoading=true", () => {
    setup({ isLoading: true, data: null });
    render(<CommunityStats />);
    expect(screen.getByTestId("community-stats-loading")).toBeInTheDocument();
  });

  it("returns null when error is set", () => {
    setup({ error: new Error("Fetch failed"), data: null });
    const { container } = render(<CommunityStats />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null when data is null", () => {
    setup({ data: null });
    const { container } = render(<CommunityStats />);
    expect(container.firstChild).toBeNull();
  });

  it("renders stats banner with user count", () => {
    setup({ data: _stats });
    render(<CommunityStats />);
    expect(screen.getByTestId("stats-banner")).toHaveTextContent("142 users");
  });

  it("renders average savings percentage when provided", () => {
    setup({ data: _stats });
    render(<CommunityStats />);
    expect(screen.getByTestId("stats-banner")).toHaveTextContent(
      "saved an average of 19%",
    );
  });

  it("omits savings text when avg_savings_pct is null", () => {
    setup({ data: { ..._stats, avg_savings_pct: null } });
    render(<CommunityStats />);
    expect(screen.getByTestId("stats-banner")).not.toHaveTextContent(
      "saved an average",
    );
  });

  it("renders attribution text with post count", () => {
    setup({ data: _stats });
    render(<CommunityStats />);
    expect(screen.getByTestId("stats-attribution")).toHaveTextContent(
      "Based on 87 reports",
    );
  });

  it("omits attribution when since is absent", () => {
    setup({ data: { ..._stats, since: null } });
    render(<CommunityStats />);
    expect(screen.queryByTestId("stats-attribution")).not.toBeInTheDocument();
  });

  it("renders top tip when provided", () => {
    setup({ data: _stats });
    render(<CommunityStats />);
    expect(screen.getByTestId("top-tip")).toBeInTheDocument();
    expect(
      screen.getByText("Switch to off-peak charging for EVs"),
    ).toBeInTheDocument();
  });

  it("omits top tip section when top_tip is null", () => {
    setup({ data: { ..._stats, top_tip: null } });
    render(<CommunityStats />);
    expect(screen.queryByTestId("top-tip")).not.toBeInTheDocument();
  });

  it("calls useCommunityStats with region from store", () => {
    setup({ data: null });
    render(<CommunityStats />);
    expect(mockUseCommunityStats).toHaveBeenCalledWith("us_ct");
  });

  it("renders community-stats container on success", () => {
    setup({ data: _stats });
    render(<CommunityStats />);
    expect(screen.getByTestId("community-stats")).toBeInTheDocument();
  });
});
