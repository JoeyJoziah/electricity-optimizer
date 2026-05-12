import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { DashboardStatsRow } from "@/components/dashboard/DashboardStatsRow";
import type { DashboardStatsRowProps } from "@/components/dashboard/DashboardTypes";
import type { Supplier } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function TrendIcon(props: React.SVGProps<SVGSVGElement>) {
  return <svg data-testid="trend-icon" {...props} />;
}

function makeSupplier(id: string, estimatedAnnualCost: number): Supplier {
  return {
    id,
    name: `Supplier ${id}`,
    avgPricePerKwh: 0.1,
    standingCharge: 0,
    greenEnergy: false,
    rating: 4,
    estimatedAnnualCost,
    tariffType: "fixed",
  };
}

const baseProps: DashboardStatsRowProps = {
  currentPrice: null,
  trend: "stable",
  TrendIcon: TrendIcon as unknown as DashboardStatsRowProps["TrendIcon"],
  savingsData: null,
  optimalWindow: null,
  forecastLoading: false,
  suppliersCount: 5,
  currentSupplier: null,
  topSuppliers: [],
};

// ---------------------------------------------------------------------------
// Tests — Current Price card
// ---------------------------------------------------------------------------

describe("DashboardStatsRow — Current Price card", () => {
  it('shows "--" when currentPrice is null', () => {
    render(<DashboardStatsRow {...baseProps} />);
    expect(screen.getByTestId("current-price")).toHaveTextContent("--");
  });

  it("shows formatted price when currentPrice is provided", () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        currentPrice={{ price: 0.12, trend: "stable", changePercent: null }}
      />,
    );
    expect(screen.getByTestId("current-price")).toHaveTextContent("$0.12");
  });

  it("applies text-danger-600 for increasing trend", () => {
    render(<DashboardStatsRow {...baseProps} trend="increasing" />);
    expect(screen.getByTestId("price-trend")).toHaveClass("text-danger-600");
  });

  it("applies text-success-600 for decreasing trend", () => {
    render(<DashboardStatsRow {...baseProps} trend="decreasing" />);
    expect(screen.getByTestId("price-trend")).toHaveClass("text-success-600");
  });

  it("applies text-gray-500 for stable trend", () => {
    render(<DashboardStatsRow {...baseProps} />);
    expect(screen.getByTestId("price-trend")).toHaveClass("text-gray-500");
  });

  it("shows positive changePercent with leading +", () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        currentPrice={{ price: 0.12, trend: "increasing", changePercent: 5.3 }}
      />,
    );
    expect(screen.getByTestId("price-trend")).toHaveTextContent("+5.3%");
  });

  it("shows negative changePercent without leading +", () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        currentPrice={{ price: 0.11, trend: "decreasing", changePercent: -2.1 }}
      />,
    );
    expect(screen.getByTestId("price-trend")).toHaveTextContent("-2.1%");
  });

  it('shows "Stable" when changePercent is null', () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        currentPrice={{ price: 0.12, trend: "stable", changePercent: null }}
      />,
    );
    expect(screen.getByTestId("price-trend")).toHaveTextContent("Stable");
  });
});

// ---------------------------------------------------------------------------
// Tests — Total Saved card
// ---------------------------------------------------------------------------

describe("DashboardStatsRow — Total Saved card", () => {
  it("shows streak badge when streak_days > 0", () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        savingsData={{
          total: 100,
          weekly: 14,
          monthly: 60,
          streak_days: 5,
          currency: "USD",
        }}
      />,
    );
    expect(screen.getByText("5-day streak")).toBeInTheDocument();
  });

  it("omits streak badge when streak_days is 0", () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        savingsData={{
          total: 100,
          weekly: 14,
          monthly: 60,
          streak_days: 0,
          currency: "USD",
        }}
      />,
    );
    expect(screen.queryByText(/streak/)).not.toBeInTheDocument();
  });

  it("shows monthly savings amount", () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        savingsData={{
          total: 100,
          weekly: 14,
          monthly: 60,
          streak_days: 0,
          currency: "USD",
        }}
      />,
    );
    expect(screen.getByText("$60.00")).toBeInTheDocument();
  });

  it('shows "Start saving to track" fallback when savingsData is null', () => {
    render(<DashboardStatsRow {...baseProps} />);
    expect(screen.getByText("Start saving to track")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — Optimal Times card
// ---------------------------------------------------------------------------

describe("DashboardStatsRow — Optimal Times card", () => {
  it("shows start/end labels and avgPrice when optimalWindow is provided", () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        optimalWindow={{ startLabel: "2am", endLabel: "6am", avgPrice: 0.08 }}
      />,
    );
    expect(screen.getByText("2am - 6am")).toBeInTheDocument();
    expect(screen.getByText(/Avg \$0\.08\/kWh/)).toBeInTheDocument();
  });

  it('shows "Loading forecast..." when forecastLoading and no window', () => {
    render(<DashboardStatsRow {...baseProps} forecastLoading={true} />);
    expect(screen.getByText("Loading forecast...")).toBeInTheDocument();
  });

  it('shows "No forecast data" when not loading and no window', () => {
    render(<DashboardStatsRow {...baseProps} />);
    expect(screen.getByText("No forecast data")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — Suppliers card
// ---------------------------------------------------------------------------

describe("DashboardStatsRow — Suppliers card", () => {
  it("shows supplier count", () => {
    render(<DashboardStatsRow {...baseProps} suppliersCount={8} />);
    expect(screen.getByText("8 options")).toBeInTheDocument();
  });

  it('shows "Cheaper available" badge when a top supplier costs less', () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        currentSupplier={{ id: "current", estimatedAnnualCost: 1200 }}
        topSuppliers={[
          makeSupplier("cheap", 900),
          makeSupplier("pricey", 1400),
        ]}
      />,
    );
    expect(screen.getByText("Cheaper available")).toBeInTheDocument();
  });

  it('omits "Cheaper available" when all top suppliers cost more', () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        currentSupplier={{ id: "current", estimatedAnnualCost: 1200 }}
        topSuppliers={[makeSupplier("pricey", 1500)]}
      />,
    );
    expect(screen.queryByText("Cheaper available")).not.toBeInTheDocument();
  });

  it('omits "Cheaper available" when currentSupplier is null', () => {
    render(
      <DashboardStatsRow
        {...baseProps}
        currentSupplier={null}
        topSuppliers={[makeSupplier("cheap", 900)]}
      />,
    );
    expect(screen.queryByText("Cheaper available")).not.toBeInTheDocument();
  });

  it('renders "Compare all" link pointing to /suppliers', () => {
    render(<DashboardStatsRow {...baseProps} />);
    const link = screen.getByRole("link", { name: /compare all/i });
    expect(link).toHaveAttribute("href", "/suppliers");
  });
});
