import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { ApiClientError } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// next/dynamic — synchronous stub resolution
// ---------------------------------------------------------------------------
jest.mock("next/dynamic", () => {
  return () => {
    const Stub = (props: Record<string, unknown>) => (
      <div
        data-testid="price-line-chart-stub"
        data-loading={String(props.loading)}
      />
    );
    Stub.displayName = "PriceLineChartStub";
    return Stub;
  };
});

// ---------------------------------------------------------------------------
// Sub-component mocks
// ---------------------------------------------------------------------------
jest.mock("@/components/gamification/SavingsTracker", () => ({
  SavingsTracker: (props: Record<string, unknown>) => (
    <div
      data-testid="savings-tracker-stub"
      data-monthly={props.monthlySavings}
      data-streak={props.streakDays}
    />
  ),
}));

jest.mock("@/components/dashboard/TeaserCards", () => ({
  SavingsTeaser: ({ region }: { region?: string }) => (
    <div data-testid="savings-teaser-stub" data-region={region} />
  ),
  ForecastTeaser: () => <div data-testid="forecast-teaser-stub" />,
}));

jest.mock("@/components/ui/skeleton", () => ({
  ChartSkeleton: () => <div data-testid="chart-skeleton-stub" />,
  Skeleton: (props: Record<string, unknown>) => (
    <div data-testid="skeleton-stub" {...props} />
  ),
}));

import { DashboardCharts } from "@/components/dashboard/DashboardCharts";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const baseProps = {
  chartData: [],
  historyLoading: false,
  timeRange: "24h" as const,
  onTimeRangeChange: jest.fn(),
  savingsData: null,
  savingsError: undefined,
  region: "us_ny",
};

const savingsData = {
  total: 200,
  weekly: 14,
  monthly: 60,
  streak_days: 5,
  currency: "USD",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DashboardCharts", () => {
  it("renders the price history card heading", () => {
    render(<DashboardCharts {...baseProps} />);
    expect(screen.getByText("Price History")).toBeInTheDocument();
  });

  it("renders View all prices link to /prices", () => {
    render(<DashboardCharts {...baseProps} />);
    const link = screen.getByRole("link", { name: /view all prices/i });
    expect(link).toHaveAttribute("href", "/prices");
  });

  it("renders PriceLineChart stub", () => {
    render(<DashboardCharts {...baseProps} />);
    expect(screen.getByTestId("price-line-chart-stub")).toBeInTheDocument();
  });

  it('shows "Savings & Streaks" heading when not tier-gated', () => {
    render(<DashboardCharts {...baseProps} />);
    expect(screen.getByText("Savings & Streaks")).toBeInTheDocument();
  });

  it("renders SavingsTracker when not tier-gated", () => {
    render(<DashboardCharts {...baseProps} savingsData={savingsData} />);
    expect(screen.getByTestId("savings-tracker-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("savings-teaser-stub")).not.toBeInTheDocument();
  });

  it("passes correct monthly savings to SavingsTracker", () => {
    render(<DashboardCharts {...baseProps} savingsData={savingsData} />);
    expect(screen.getByTestId("savings-tracker-stub")).toHaveAttribute(
      "data-monthly",
      "60",
    );
  });

  it("passes streak_days to SavingsTracker", () => {
    render(<DashboardCharts {...baseProps} savingsData={savingsData} />);
    expect(screen.getByTestId("savings-tracker-stub")).toHaveAttribute(
      "data-streak",
      "5",
    );
  });

  it('shows "Your Potential Savings" heading when savings error is 403', () => {
    const err = new ApiClientError({ message: "Forbidden", status: 403 });
    render(<DashboardCharts {...baseProps} savingsError={err} />);
    expect(screen.getByText("Your Potential Savings")).toBeInTheDocument();
  });

  it("renders SavingsTeaser when savings error is 403", () => {
    const err = new ApiClientError({ message: "Forbidden", status: 403 });
    render(<DashboardCharts {...baseProps} savingsError={err} />);
    expect(screen.getByTestId("savings-teaser-stub")).toBeInTheDocument();
    expect(
      screen.queryByTestId("savings-tracker-stub"),
    ).not.toBeInTheDocument();
  });

  it("passes region to SavingsTeaser", () => {
    const err = new ApiClientError({ message: "Forbidden", status: 403 });
    render(
      <DashboardCharts {...baseProps} savingsError={err} region="us_ct" />,
    );
    expect(screen.getByTestId("savings-teaser-stub")).toHaveAttribute(
      "data-region",
      "us_ct",
    );
  });

  it("renders SavingsTracker (not teaser) for non-403 errors", () => {
    const err = new ApiClientError({ message: "Server error", status: 500 });
    render(<DashboardCharts {...baseProps} savingsError={err} />);
    expect(screen.getByTestId("savings-tracker-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("savings-teaser-stub")).not.toBeInTheDocument();
  });
});
