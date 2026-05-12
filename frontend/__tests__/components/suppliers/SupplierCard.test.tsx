import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { SupplierCard } from "@/components/suppliers/SupplierCard";
import type { Supplier } from "@/types";

jest.mock("next/image", () => ({
  __esModule: true,
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...props} alt={props.alt ?? ""} />
  ),
}));
jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));
jest.mock("@/lib/utils/format", () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
}));
jest.mock("@/components/ui/card", () => ({
  Card: ({ children, ...rest }: React.HTMLAttributes<HTMLDivElement>) => (
    <div {...rest}>{children}</div>
  ),
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
jest.mock("lucide-react", () => ({
  Star: () => <svg data-testid="star-icon" />,
  Leaf: () => <svg data-testid="leaf-icon" />,
  Zap: () => <svg data-testid="zap-icon" />,
  Check: () => <svg data-testid="check-icon" />,
}));

const baseSupplier: Supplier = {
  id: "sup-1",
  name: "GreenPower Co",
  rating: 4.5,
  logo: null,
  estimatedAnnualCost: 1000,
  ratePerKwh: 0.12,
  avgPricePerKwh: 0.12,
  isGreenEnergy: false,
  contractLengthMonths: 12,
  exitFee: 50,
  description: "Test supplier",
  availableRegions: ["CT"],
} as unknown as Supplier;

describe("SupplierCard", () => {
  it("renders supplier name", () => {
    render(<SupplierCard supplier={baseSupplier} />);
    expect(screen.getByText("GreenPower Co")).toBeInTheDocument();
  });

  it("renders the card with correct data-testid", () => {
    render(<SupplierCard supplier={baseSupplier} />);
    expect(screen.getByTestId("supplier-card-sup-1")).toBeInTheDocument();
  });

  it("shows logo placeholder when no logo provided", () => {
    render(<SupplierCard supplier={baseSupplier} />);
    expect(screen.getByTestId("supplier-logo-placeholder")).toBeInTheDocument();
  });

  it("renders img tag when logo is provided", () => {
    const withLogo = { ...baseSupplier, logo: "/logo.png" };
    render(<SupplierCard supplier={withLogo} />);
    expect(screen.getByAltText("GreenPower Co logo")).toBeInTheDocument();
  });

  it("shows 'Current Supplier' badge when isCurrent=true", () => {
    render(<SupplierCard supplier={baseSupplier} isCurrent />);
    expect(screen.getByText("Current Supplier")).toBeInTheDocument();
  });

  it("shows savings when currentAnnualCost is higher than supplier cost", () => {
    render(<SupplierCard supplier={baseSupplier} currentAnnualCost={1200} />);
    expect(screen.getByText(/Save \$200.00/)).toBeInTheDocument();
  });

  it("does not show savings when supplier costs more", () => {
    render(<SupplierCard supplier={baseSupplier} currentAnnualCost={800} />);
    expect(screen.queryByText(/Save/)).not.toBeInTheDocument();
  });

  it("calls onSelect when select button is clicked", () => {
    const onSelect = jest.fn();
    render(<SupplierCard supplier={baseSupplier} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /switch to/i }));
    expect(onSelect).toHaveBeenCalledWith(baseSupplier);
  });
});
