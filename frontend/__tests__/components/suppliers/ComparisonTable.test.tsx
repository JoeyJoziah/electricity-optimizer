import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { ComparisonTable } from "@/components/suppliers/ComparisonTable";
import type { Supplier } from "@/types";

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));
jest.mock("@/lib/utils/format", () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
}));
jest.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => (
    <span>{children}</span>
  ),
}));
jest.mock("@/components/ui/button", () => ({
  Button: (
    props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
      children: React.ReactNode;
    },
  ) => <button {...props}>{props.children}</button>,
}));
jest.mock("@/components/ui/input", () => ({
  Checkbox: (props: React.InputHTMLAttributes<HTMLInputElement>) => (
    <input type="checkbox" {...props} />
  ),
}));
jest.mock("lucide-react", () => ({
  Star: () => <svg />,
  Leaf: () => <svg />,
  ChevronUp: () => <svg />,
  ChevronDown: () => <svg />,
  ArrowUpDown: () => <svg />,
}));

function makeSupplier(id: string, cost: number, green = false): Supplier {
  return {
    id,
    name: `Supplier ${id}`,
    rating: 4.0,
    avgPricePerKwh: cost / 1000,
    estimatedAnnualCost: cost,
    standingCharge: 0,
    greenEnergy: green,
    logo: null,
    contractLengthMonths: 12,
    exitFee: 0,
    availableRegions: ["CT"],
  } as unknown as Supplier;
}

const suppliers = [
  makeSupplier("a", 1000),
  makeSupplier("b", 800),
  makeSupplier("c-green", 900, true),
];

describe("ComparisonTable", () => {
  it("renders a row per supplier", () => {
    render(<ComparisonTable suppliers={suppliers} />);
    expect(screen.getByTestId("supplier-row-a")).toBeInTheDocument();
    expect(screen.getByTestId("supplier-row-b")).toBeInTheDocument();
    expect(screen.getByTestId("supplier-row-c-green")).toBeInTheDocument();
  });

  it("calls onSelect when a row switch button is clicked", () => {
    const onSelect = jest.fn();
    render(
      <ComparisonTable
        suppliers={[makeSupplier("x", 1000)]}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /switch/i }));
    expect(onSelect).toHaveBeenCalled();
  });

  it("shows green badge for green energy suppliers", () => {
    render(<ComparisonTable suppliers={suppliers} />);
    expect(screen.getByTestId("green-badge")).toBeInTheDocument();
  });

  it("renders the table element", () => {
    render(<ComparisonTable suppliers={suppliers} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("shows green-only checkbox filter when showFilters=true", () => {
    render(<ComparisonTable suppliers={suppliers} showFilters />);
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
  });

  it("filters to green suppliers when green-only is checked", () => {
    render(<ComparisonTable suppliers={suppliers} showFilters />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByTestId("supplier-row-c-green")).toBeInTheDocument();
    expect(screen.queryByTestId("supplier-row-a")).not.toBeInTheDocument();
  });
});
