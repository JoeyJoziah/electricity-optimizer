import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { SwitchWizard } from "@/components/suppliers/SwitchWizard";
import type { Supplier } from "@/types";

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));
jest.mock("@/lib/utils/format", () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
  formatPercentage: (v: number) => `${v}%`,
}));
jest.mock("@/components/ui/button", () => ({
  Button: (
    props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
      children: React.ReactNode;
      loading?: boolean;
    },
  ) => (
    <button disabled={props.disabled} onClick={props.onClick}>
      {props.children}
    </button>
  ),
}));
jest.mock("@/components/ui/card", () => ({
  Card: ({ children, ...rest }: React.HTMLAttributes<HTMLDivElement>) => (
    <div {...rest}>{children}</div>
  ),
  CardContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => (
    <span>{children}</span>
  ),
}));
jest.mock("lucide-react", () => ({
  ArrowRight: () => <svg />,
  ArrowLeft: () => <svg />,
  Check: () => <svg />,
  X: () => <svg />,
  AlertTriangle: () => <svg />,
  Shield: () => <svg />,
  FileText: () => <svg />,
  Leaf: () => <svg />,
  Loader2: () => <svg />,
  CheckCircle2: () => <svg />,
  Star: () => <svg />,
  Zap: () => <svg />,
}));

function makeSupplier(id: string): Supplier {
  return {
    id,
    name: `Supplier ${id}`,
    rating: 4.2,
    avgPricePerKwh: 0.12,
    estimatedAnnualCost: 900,
    greenEnergy: false,
    contractLengthMonths: 12,
    exitFee: 0,
    logo: null,
    availableRegions: ["CT"],
  } as unknown as Supplier;
}

const recommendation = {
  supplier: makeSupplier("new"),
  currentSupplier: makeSupplier("current"),
  estimatedSavings: 100,
  paybackMonths: 3,
  confidence: 0.85,
};

describe("SwitchWizard", () => {
  it("renders the wizard with aria role=region", () => {
    render(<SwitchWizard recommendation={recommendation} />);
    expect(
      screen.getByRole("region", { name: /supplier switching wizard/i }),
    ).toBeInTheDocument();
  });

  it("shows Step 1 of 4 initially", () => {
    render(<SwitchWizard recommendation={recommendation} />);
    expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
  });

  it("advances to step 2 when Next is clicked", () => {
    render(<SwitchWizard recommendation={recommendation} />);
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("Step 2 of 4")).toBeInTheDocument();
  });

  it("goes back to step 1 when Back is clicked on step 2", () => {
    render(<SwitchWizard recommendation={recommendation} />);
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = jest.fn();
    render(
      <SwitchWizard recommendation={recommendation} onCancel={onCancel} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });
});
