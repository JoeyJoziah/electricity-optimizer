import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import CurrentPlanCard from "@/components/auto-switcher/CurrentPlanCard";
import type { SwitchDecision } from "@/lib/api/agent-switcher";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

jest.mock("lucide-react", () => ({
  Zap: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-zap" {...props} />
  ),
}));

jest.mock("@/components/ui/card", () => ({
  Card: ({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => (
    <div data-testid="card" className={className}>
      {children}
    </div>
  ),
  CardHeader: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card-header">{children}</div>
  ),
  CardTitle: ({ children }: { children: React.ReactNode }) => (
    <h2 data-testid="card-title">{children}</h2>
  ),
  CardContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card-content">{children}</div>
  ),
}));

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={className} />
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePlan(overrides: Record<string, unknown> = {}) {
  return {
    id: "plan-1",
    plan_name: "Fixed Rate 12",
    provider_name: "Eversource",
    rate_kwh: 0.1234,
    fixed_charge: 9.99,
    term_months: 12,
    etf_amount: 0,
    green_energy_pct: 0,
    ...overrides,
  };
}

function makeDecision(plan: Record<string, unknown> | null) {
  return {
    id: "dec-1",
    action: "hold",
    current_plan: plan,
  } as unknown as SwitchDecision;
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe("CurrentPlanCard — loading", () => {
  it("renders skeleton elements while loading", () => {
    render(<CurrentPlanCard decision={null} isLoading={true} />);
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0);
  });

  it("does not render plan data while loading", () => {
    render(<CurrentPlanCard decision={null} isLoading={true} />);
    expect(screen.queryByText("Current Plan")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Empty / no plan
// ---------------------------------------------------------------------------

describe("CurrentPlanCard — no plan", () => {
  it("renders 'Current Plan' title when decision has no plan", () => {
    render(<CurrentPlanCard decision={null} isLoading={false} />);
    expect(screen.getByTestId("card-title")).toHaveTextContent("Current Plan");
  });

  it("shows empty-state message when no plan detected", () => {
    render(<CurrentPlanCard decision={null} isLoading={false} />);
    expect(screen.getByText(/No current plan detected/i)).toBeInTheDocument();
  });

  it("renders Zap icon in empty state", () => {
    render(<CurrentPlanCard decision={null} isLoading={false} />);
    expect(screen.getByTestId("icon-zap")).toBeInTheDocument();
  });

  it("shows empty state when decision has current_plan=null", () => {
    render(<CurrentPlanCard decision={makeDecision(null)} isLoading={false} />);
    expect(screen.getByText(/No current plan detected/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Plan data rendering
// ---------------------------------------------------------------------------

describe("CurrentPlanCard — with plan", () => {
  it("renders plan name", () => {
    render(
      <CurrentPlanCard decision={makeDecision(makePlan())} isLoading={false} />,
    );
    expect(screen.getByText("Fixed Rate 12")).toBeInTheDocument();
  });

  it("renders provider name", () => {
    render(
      <CurrentPlanCard decision={makeDecision(makePlan())} isLoading={false} />,
    );
    expect(screen.getByText("Eversource")).toBeInTheDocument();
  });

  it("renders rate formatted with /kWh suffix", () => {
    render(
      <CurrentPlanCard
        decision={makeDecision(makePlan({ rate_kwh: 0.1234 }))}
        isLoading={false}
      />,
    );
    expect(screen.getByText("$0.1234/kWh")).toBeInTheDocument();
  });

  it("renders fixed charge formatted as currency", () => {
    render(
      <CurrentPlanCard
        decision={makeDecision(makePlan({ fixed_charge: 9.99 }))}
        isLoading={false}
      />,
    );
    expect(screen.getByText("$9.99/mo")).toBeInTheDocument();
  });

  it("renders contract term row when term_months is set", () => {
    render(
      <CurrentPlanCard
        decision={makeDecision(makePlan({ term_months: 24 }))}
        isLoading={false}
      />,
    );
    expect(screen.getByText("24 months")).toBeInTheDocument();
  });

  it("does NOT render contract term row when term_months is null", () => {
    render(
      <CurrentPlanCard
        decision={makeDecision(makePlan({ term_months: null }))}
        isLoading={false}
      />,
    );
    expect(screen.queryByText(/months/)).not.toBeInTheDocument();
  });

  it("does NOT render ETF row when etf_amount is 0", () => {
    render(
      <CurrentPlanCard
        decision={makeDecision(makePlan({ etf_amount: 0 }))}
        isLoading={false}
      />,
    );
    expect(screen.queryByText("Early Termination Fee")).not.toBeInTheDocument();
  });

  it("renders ETF row when etf_amount > 0", () => {
    render(
      <CurrentPlanCard
        decision={makeDecision(makePlan({ etf_amount: 150 }))}
        isLoading={false}
      />,
    );
    expect(screen.getByText("Early Termination Fee")).toBeInTheDocument();
    expect(screen.getByText("$150.00")).toBeInTheDocument();
  });
});
