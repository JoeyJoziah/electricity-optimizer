import { render, screen } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { PriceLineChart } from "@/components/charts/PriceLineChart";
import type { PriceDataPoint } from "@/types";

jest.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: ({ dataKey }: { dataKey: string }) => (
    <div data-testid={`line-${dataKey}`} />
  ),
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ReferenceArea: () => <div />,
}));
jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));
jest.mock("@/lib/utils/format", () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
}));
jest.mock("@/lib/constants/chartTokens", () => ({
  chartColor: () => "#0000ff",
  chartTooltipStyleWithShadow: {},
}));
jest.mock("date-fns", () => ({
  format: (_: Date, fmt: string) => (fmt === "HH:mm" ? "10:00" : "Jan 01"),
  parseISO: (s: string) => new Date(s),
}));
jest.mock("lucide-react", () => ({
  TrendingUp: () => <svg data-testid="trending-up" />,
  TrendingDown: () => <svg data-testid="trending-down" />,
  Minus: () => <svg data-testid="trending-stable" />,
}));

function makePoint(
  time: string,
  price: number | null,
  forecast: number | null = null,
): PriceDataPoint {
  return { time, price, forecast } as unknown as PriceDataPoint;
}

describe("PriceLineChart", () => {
  it("shows loading skeleton when loading=true", () => {
    render(<PriceLineChart data={[]} loading />);
    const container = screen.getByTestId("price-chart-container");
    expect(container).toBeInTheDocument();
    // Loading state renders a skeleton, not the actual chart
    expect(screen.queryByTestId("line-chart")).not.toBeInTheDocument();
  });

  it("shows empty state when data is empty and not loading", () => {
    render(<PriceLineChart data={[]} />);
    expect(
      screen.getByRole("img", { name: /no data available/i }),
    ).toBeInTheDocument();
  });

  it("renders the line chart with data", () => {
    const data = [
      makePoint("2024-06-01T10:00:00", 0.12),
      makePoint("2024-06-01T11:00:00", 0.14),
    ];
    render(<PriceLineChart data={data} />);
    expect(
      screen.getByRole("img", { name: /price chart showing actual/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });

  it("shows current price when showCurrentPrice=true and data has prices", () => {
    const data = [makePoint("2024-06-01T10:00:00", 0.12)];
    render(<PriceLineChart data={data} showCurrentPrice />);
    expect(screen.getByTestId("current-price")).toBeInTheDocument();
  });

  it("shows trend badge when showTrend=true", () => {
    const data = [
      makePoint("2024-06-01T08:00:00", 0.1),
      makePoint("2024-06-01T09:00:00", 0.1),
      makePoint("2024-06-01T10:00:00", 0.1),
      makePoint("2024-06-01T11:00:00", 0.1),
    ];
    render(<PriceLineChart data={data} showTrend />);
    expect(screen.getByTestId("price-trend")).toBeInTheDocument();
  });
});
