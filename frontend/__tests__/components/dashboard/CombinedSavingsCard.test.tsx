import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { CombinedSavingsCard } from "@/components/dashboard/CombinedSavingsCard";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseCombinedSavings = jest.fn();

jest.mock("@/lib/hooks/useCombinedSavings", () => ({
  useCombinedSavings: () => mockUseCombinedSavings(),
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
  total_monthly_savings: "45.00",
  breakdown: [
    { utility_type: "electricity", monthly_savings: "30.00" },
    { utility_type: "natural_gas", monthly_savings: "15.00" },
  ],
  savings_rank_pct: 0.2,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CombinedSavingsCard", () => {
  beforeEach(() => {
    mockUseCombinedSavings.mockReset();
  });

  it("shows loading skeleton when isLoading is true", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: true,
      data: undefined,
      error: null,
    });
    render(<CombinedSavingsCard />);
    expect(screen.getByTestId("combined-savings-loading")).toBeInTheDocument();
    expect(
      screen.queryByTestId("combined-savings-card"),
    ).not.toBeInTheDocument();
  });

  it("shows error state when error is set", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: undefined,
      error: new Error("fetch failed"),
    });
    render(<CombinedSavingsCard />);
    expect(screen.getByTestId("combined-savings-error")).toBeInTheDocument();
    expect(
      screen.getByText(/unable to load combined savings/i),
    ).toBeInTheDocument();
  });

  it("shows error state when data is null", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: null,
      error: null,
    });
    render(<CombinedSavingsCard />);
    expect(screen.getByTestId("combined-savings-error")).toBeInTheDocument();
  });

  it("renders populated card with total savings", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: _data,
      error: null,
    });
    render(<CombinedSavingsCard />);
    expect(screen.getByTestId("combined-savings-card")).toBeInTheDocument();
    expect(screen.getByText("$45.00")).toBeInTheDocument();
  });

  it("renders the savings bar element", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: _data,
      error: null,
    });
    render(<CombinedSavingsCard />);
    expect(screen.getByTestId("savings-bar")).toBeInTheDocument();
  });

  it("renders breakdown labels for each utility", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: _data,
      error: null,
    });
    render(<CombinedSavingsCard />);
    expect(screen.getByText(/electricity.*\$30\.00/)).toBeInTheDocument();
    expect(screen.getByText(/natural gas.*\$15\.00/)).toBeInTheDocument();
  });

  it("shows percentile badge with correct text when savings_rank_pct is set", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: _data, // savings_rank_pct: 0.2 → Top 80%
      error: null,
    });
    render(<CombinedSavingsCard />);
    const badge = screen.getByTestId("savings-percentile");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("Top 80% of savers");
  });

  it("omits percentile badge when savings_rank_pct is null", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: { ..._data, savings_rank_pct: null },
      error: null,
    });
    render(<CombinedSavingsCard />);
    expect(screen.queryByTestId("savings-percentile")).not.toBeInTheDocument();
  });

  it("renders savings bar segments for each breakdown entry", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: _data,
      error: null,
    });
    render(<CombinedSavingsCard />);
    const bar = screen.getByTestId("savings-bar");
    // Two segments inside the bar div (one per utility)
    expect(bar.children).toHaveLength(2);
  });

  it("applies correct color class to electricity segment", () => {
    mockUseCombinedSavings.mockReturnValue({
      isLoading: false,
      data: _data,
      error: null,
    });
    render(<CombinedSavingsCard />);
    const bar = screen.getByTestId("savings-bar");
    expect(bar.firstElementChild).toHaveClass("bg-yellow-400");
  });
});
