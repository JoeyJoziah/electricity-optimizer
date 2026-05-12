import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { NeighborhoodCard } from "@/components/dashboard/NeighborhoodCard";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseNeighborhoodComparison = jest.fn();
const mockUseSettingsStore = jest.fn();

jest.mock("@/lib/hooks/useNeighborhood", () => ({
  useNeighborhoodComparison: (...args: unknown[]) =>
    mockUseNeighborhoodComparison(...args),
}));

jest.mock("@/lib/store/settings", () => ({
  useSettingsStore: (selector: (s: Record<string, unknown>) => unknown) =>
    mockUseSettingsStore(selector),
}));

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: (props: Record<string, unknown>) => (
    <div data-testid="skeleton" {...props} />
  ),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const _data = {
  user_rate: "0.1200",
  avg_rate: "0.1400",
  percentile: 0.7,
  cheapest_supplier: "GreenPower",
  potential_savings: "0.0200",
  neighbor_count: 50,
};

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockUseSettingsStore.mockImplementation(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ region: "us_ny" }),
  );
  mockUseNeighborhoodComparison.mockReset();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("NeighborhoodCard", () => {
  it("shows loading skeleton when isLoading is true", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: true,
      data: undefined,
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(screen.getByTestId("neighborhood-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("neighborhood-card")).not.toBeInTheDocument();
  });

  it("shows error state when error is set", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: undefined,
      error: new Error("network error"),
    });
    render(<NeighborhoodCard />);
    expect(screen.getByTestId("neighborhood-error")).toBeInTheDocument();
    expect(
      screen.getByText(/unable to load neighborhood comparison/i),
    ).toBeInTheDocument();
  });

  it("shows error state when data is null", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: null,
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(screen.getByTestId("neighborhood-error")).toBeInTheDocument();
  });

  it("shows insufficient data state when percentile is null", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: { ..._data, percentile: null },
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(screen.getByTestId("neighborhood-insufficient")).toBeInTheDocument();
    expect(screen.getByText(/check back soon/i)).toBeInTheDocument();
  });

  it("shows insufficient data state when user_rate is null", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: { ..._data, user_rate: null },
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(screen.getByTestId("neighborhood-insufficient")).toBeInTheDocument();
  });

  it("renders populated card with rate context", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: _data,
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(screen.getByTestId("neighborhood-card")).toBeInTheDocument();
    expect(screen.getByTestId("neighborhood-context")).toHaveTextContent(
      "0.1200",
    );
    expect(screen.getByTestId("neighborhood-context")).toHaveTextContent(
      "0.1400",
    );
  });

  it("renders neighborhood bars", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: _data,
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(screen.getByTestId("neighborhood-bars")).toBeInTheDocument();
  });

  it("shows percentile text", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: _data, // percentile: 0.7 → 70%
      error: null,
    });
    render(<NeighborhoodCard />);
    const pct = screen.getByTestId("neighborhood-percentile");
    expect(pct).toHaveTextContent("70%");
  });

  it("shows cheapest supplier savings when potential_savings > 0", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: _data,
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(screen.getByTestId("neighborhood-savings")).toBeInTheDocument();
    expect(screen.getByTestId("neighborhood-savings")).toHaveTextContent(
      "GreenPower",
    );
  });

  it("omits savings hint when potential_savings is 0", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: { ..._data, potential_savings: "0.0000" },
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(
      screen.queryByTestId("neighborhood-savings"),
    ).not.toBeInTheDocument();
  });

  it("omits savings hint when cheapest_supplier is null", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: false,
      data: { ..._data, cheapest_supplier: null },
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(
      screen.queryByTestId("neighborhood-savings"),
    ).not.toBeInTheDocument();
  });

  it("passes region and utility_type to useNeighborhoodComparison", () => {
    mockUseNeighborhoodComparison.mockReturnValue({
      isLoading: true,
      data: undefined,
      error: null,
    });
    render(<NeighborhoodCard />);
    expect(mockUseNeighborhoodComparison).toHaveBeenCalledWith(
      "us_ny",
      "electricity",
    );
  });
});
