import { render, screen } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { SavingsDonut } from "@/components/charts/SavingsDonut";
import type { SavingsData } from "@/components/charts/SavingsDonut";

jest.mock("recharts", () => ({
  PieChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  Pie: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pie">{children}</div>
  ),
  Cell: ({ fill }: { fill: string }) => (
    <div data-testid="cell" data-fill={fill} />
  ),
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  Tooltip: () => <div data-testid="tooltip" />,
}));

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));
jest.mock("@/lib/constants/chartTokens", () => ({
  CHART_COLORS: ["#ff0000", "#00ff00", "#0000ff"],
  chartTooltipStyle: {},
}));

const emptySavings: SavingsData = {
  totalSavings: 0,
  breakdown: [],
  period: "month",
};

const filledSavings: SavingsData = {
  totalSavings: 120,
  breakdown: [
    { category: "Lighting", amount: 60, percentage: 50 },
    { category: "HVAC", amount: 60, percentage: 50 },
  ],
  period: "month",
};

describe("SavingsDonut", () => {
  it("shows empty state when totalSavings is 0", () => {
    render(<SavingsDonut data={emptySavings} />);
    expect(screen.getByText("No savings yet")).toBeInTheDocument();
    expect(screen.getByText("This month")).toBeInTheDocument();
  });

  it("renders the pie chart when savings exist", () => {
    render(<SavingsDonut data={filledSavings} />);
    expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
  });

  it("displays total savings amount in center", () => {
    render(<SavingsDonut data={filledSavings} />);
    expect(screen.getByText("$120.00")).toBeInTheDocument();
  });

  it("shows period label in center", () => {
    render(<SavingsDonut data={filledSavings} />);
    expect(screen.getByText("This month")).toBeInTheDocument();
  });

  it("does not render legend items by default", () => {
    render(<SavingsDonut data={filledSavings} />);
    expect(screen.queryByTestId("legend-item")).not.toBeInTheDocument();
  });

  it("renders legend items when showLegend=true", () => {
    render(<SavingsDonut data={filledSavings} showLegend />);
    expect(screen.getAllByTestId("legend-item")).toHaveLength(2);
    expect(screen.getByText("Lighting")).toBeInTheDocument();
    expect(screen.getByText("HVAC")).toBeInTheDocument();
  });

  it("uses accessible aria-label on chart", () => {
    render(<SavingsDonut data={filledSavings} />);
    expect(
      screen.getByRole("img", { name: /savings chart showing \$120.00/i }),
    ).toBeInTheDocument();
  });

  it("uses accessible aria-label on empty state", () => {
    render(<SavingsDonut data={emptySavings} />);
    expect(
      screen.getByRole("img", { name: /no savings yet/i }),
    ).toBeInTheDocument();
  });
});
