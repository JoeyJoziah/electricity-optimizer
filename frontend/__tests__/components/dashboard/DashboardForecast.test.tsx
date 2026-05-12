import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { ApiClientError } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// next/dynamic — synchronous stub resolution
// ---------------------------------------------------------------------------
jest.mock("next/dynamic", () => {
  return () => {
    const Stub = () => <div data-testid="forecast-chart-stub" />;
    Stub.displayName = "ForecastChartStub";
    return Stub;
  };
});

// ---------------------------------------------------------------------------
// Sub-component mocks
// ---------------------------------------------------------------------------
jest.mock("@/components/suppliers/SupplierCard", () => ({
  SupplierCard: ({
    supplier,
    isCurrent,
  }: {
    supplier: { id: string; name: string };
    isCurrent: boolean;
  }) => (
    <div
      data-testid={`supplier-card-${supplier.id}`}
      data-current={String(isCurrent)}
    >
      {supplier.name}
    </div>
  ),
}));

jest.mock("@/components/dashboard/TeaserCards", () => ({
  ForecastTeaser: () => <div data-testid="forecast-teaser-stub" />,
  SavingsTeaser: ({ region }: { region?: string }) => (
    <div data-testid="savings-teaser-stub" data-region={region} />
  ),
}));

jest.mock("@/components/ui/skeleton", () => ({
  ChartSkeleton: () => <div data-testid="chart-skeleton-stub" />,
  Skeleton: (props: Record<string, unknown>) => (
    <div data-testid="skeleton-stub" {...props} />
  ),
}));

import { DashboardForecast } from "@/components/dashboard/DashboardForecast";
import type { Supplier } from "@/types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSupplier(id: string): Supplier {
  return {
    id,
    name: `Supplier ${id}`,
    avgPricePerKwh: 0.1,
    standingCharge: 0,
    greenEnergy: false,
    rating: 4,
    estimatedAnnualCost: 1200,
    tariffType: "fixed",
  };
}

const baseProps = {
  forecastData: null,
  forecastLoading: false,
  forecastError: undefined,
  currentPrice: null,
  topSuppliers: [],
  currentSupplier: null,
};

const forecastWithPrices = {
  forecast: {
    prices: [
      { price_per_kwh: "0.10", timestamp: "2026-05-12T01:00:00Z" },
      { price_per_kwh: "0.11", timestamp: "2026-05-12T02:00:00Z" },
    ],
  },
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DashboardForecast", () => {
  it("renders the 24-Hour Forecast heading", () => {
    render(<DashboardForecast {...baseProps} />);
    expect(screen.getByText("24-Hour Forecast")).toBeInTheDocument();
  });

  it("shows Skeleton when forecastLoading is true", () => {
    render(<DashboardForecast {...baseProps} forecastLoading={true} />);
    expect(screen.getByTestId("skeleton-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("forecast-chart-stub")).not.toBeInTheDocument();
  });

  it("shows ForecastTeaser when forecastError is 403", () => {
    const err = new ApiClientError({ message: "Forbidden", status: 403 });
    render(<DashboardForecast {...baseProps} forecastError={err} />);
    expect(screen.getByTestId("forecast-teaser-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("forecast-chart-stub")).not.toBeInTheDocument();
  });

  it('shows "Forecast unavailable" when no data and no error', () => {
    render(<DashboardForecast {...baseProps} />);
    expect(screen.getByText("Forecast unavailable")).toBeInTheDocument();
  });

  it("renders ForecastChart when forecastData has prices", () => {
    render(
      <DashboardForecast {...baseProps} forecastData={forecastWithPrices} />,
    );
    expect(screen.getByTestId("forecast-chart-stub")).toBeInTheDocument();
    expect(screen.queryByText("Forecast unavailable")).not.toBeInTheDocument();
  });

  it("renders ForecastChart when forecastData.forecast is an array", () => {
    const arrayForecast = {
      forecast: [
        { hour: 1, price: 0.1, confidence: [0.085, 0.115], timestamp: "t1" },
      ],
    };
    render(<DashboardForecast {...baseProps} forecastData={arrayForecast} />);
    expect(screen.getByTestId("forecast-chart-stub")).toBeInTheDocument();
  });

  it("renders Top Suppliers heading", () => {
    render(<DashboardForecast {...baseProps} />);
    expect(screen.getByText("Top Suppliers")).toBeInTheDocument();
  });

  it("renders View all link to /suppliers", () => {
    render(<DashboardForecast {...baseProps} />);
    const link = screen.getByRole("link", { name: /view all/i });
    expect(link).toHaveAttribute("href", "/suppliers");
  });

  it("renders a SupplierCard for each topSupplier", () => {
    const suppliers = [makeSupplier("s1"), makeSupplier("s2")];
    render(<DashboardForecast {...baseProps} topSuppliers={suppliers} />);
    expect(screen.getByTestId("supplier-card-s1")).toBeInTheDocument();
    expect(screen.getByTestId("supplier-card-s2")).toBeInTheDocument();
  });

  it("marks the current supplier as isCurrent=true", () => {
    const suppliers = [makeSupplier("s1"), makeSupplier("s2")];
    render(
      <DashboardForecast
        {...baseProps}
        topSuppliers={suppliers}
        currentSupplier={{ id: "s1", estimatedAnnualCost: 1200 }}
      />,
    );
    expect(screen.getByTestId("supplier-card-s1")).toHaveAttribute(
      "data-current",
      "true",
    );
    expect(screen.getByTestId("supplier-card-s2")).toHaveAttribute(
      "data-current",
      "false",
    );
  });

  it("renders empty suppliers list without errors", () => {
    render(<DashboardForecast {...baseProps} topSuppliers={[]} />);
    expect(screen.getByText("Top Suppliers")).toBeInTheDocument();
  });

  it("does not show ForecastTeaser for non-403 errors", () => {
    const err = new ApiClientError({ message: "Server error", status: 500 });
    render(<DashboardForecast {...baseProps} forecastError={err} />);
    expect(
      screen.queryByTestId("forecast-teaser-stub"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Forecast unavailable")).toBeInTheDocument();
  });
});
