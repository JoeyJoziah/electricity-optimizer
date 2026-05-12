import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import CheckNowResult from "@/components/auto-switcher/CheckNowResult";
import type { SwitchDecision } from "@/lib/api/agent-switcher";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

jest.mock("lucide-react", () => ({
  X: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-x" {...props} />
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
  CardTitle: ({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => (
    <h2 data-testid="card-title" className={className}>
      {children}
    </h2>
  ),
  CardContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card-content">{children}</div>
  ),
}));

jest.mock("@/components/ui/badge", () => ({
  Badge: ({
    children,
    variant,
  }: {
    children: React.ReactNode;
    variant?: string;
  }) => (
    <span data-testid="badge" data-variant={variant}>
      {children}
    </span>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDecision(overrides: Partial<SwitchDecision> = {}): SwitchDecision {
  return {
    id: "dec-1",
    action: "hold",
    reason: "Rates are competitive.",
    confidence: 0,
    current_plan: null,
    proposed_plan: null,
    projected_savings_monthly: 0,
    projected_savings_annual: 0,
    net_savings_year1: 0,
    executed_at: null,
    created_at: "2026-05-12T00:00:00Z",
    ...overrides,
  } as SwitchDecision;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CheckNowResult", () => {
  it("renders the evaluation result heading", () => {
    render(<CheckNowResult result={makeDecision()} onDismiss={jest.fn()} />);
    expect(screen.getByTestId("card-title")).toHaveTextContent(
      "Evaluation Result",
    );
  });

  it("renders the decision badge with correct label for 'switch'", () => {
    render(
      <CheckNowResult
        result={makeDecision({ action: "switch" })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByTestId("badge")).toHaveTextContent("Switched");
  });

  it("renders the decision badge with correct label for 'recommend'", () => {
    render(
      <CheckNowResult
        result={makeDecision({ action: "recommend" })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByTestId("badge")).toHaveTextContent("Recommendation");
  });

  it("renders the reason text", () => {
    const reason = "Switching could save $12/month.";
    render(
      <CheckNowResult
        result={makeDecision({ reason })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByText(reason)).toBeInTheDocument();
  });

  it("calls onDismiss when dismiss button is clicked", async () => {
    const onDismiss = jest.fn();
    render(<CheckNowResult result={makeDecision()} onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("does NOT render proposed plan section when proposed_plan is null", () => {
    render(
      <CheckNowResult
        result={makeDecision({ proposed_plan: null })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.queryByText("Proposed Plan")).not.toBeInTheDocument();
  });

  it("renders proposed plan section when proposed_plan is present", () => {
    const result = makeDecision({
      proposed_plan: {
        id: "plan-1",
        plan_name: "GreenRate Flex",
        provider_name: "CleanEnergy Co",
        rate_kwh: 0.095,
        fixed_charge: 5.0,
        term_months: 12,
        etf_amount: 0,
        green_energy_pct: 100,
      } as any,
    });
    render(<CheckNowResult result={result} onDismiss={jest.fn()} />);
    expect(screen.getByText("Proposed Plan")).toBeInTheDocument();
    expect(screen.getByText("GreenRate Flex")).toBeInTheDocument();
    expect(screen.getByText("CleanEnergy Co")).toBeInTheDocument();
  });

  it("does NOT render savings section when both savings are zero", () => {
    render(
      <CheckNowResult
        result={makeDecision({
          projected_savings_monthly: 0,
          projected_savings_annual: 0,
        })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.queryByText("Monthly Savings")).not.toBeInTheDocument();
  });

  it("renders savings section when monthly savings > 0", () => {
    render(
      <CheckNowResult
        result={makeDecision({ projected_savings_monthly: 15.5 })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByText("Monthly Savings")).toBeInTheDocument();
  });

  it("renders savings section when annual savings > 0", () => {
    render(
      <CheckNowResult
        result={makeDecision({ projected_savings_annual: 180 })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByText("Annual Savings")).toBeInTheDocument();
  });

  it("does NOT render Net Year 1 row when net_savings_year1 is 0", () => {
    render(
      <CheckNowResult
        result={makeDecision({
          projected_savings_monthly: 15,
          net_savings_year1: 0,
        })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.queryByText(/Net Year 1/i)).not.toBeInTheDocument();
  });

  it("renders Net Year 1 row when net_savings_year1 > 0", () => {
    render(
      <CheckNowResult
        result={makeDecision({
          projected_savings_monthly: 10,
          net_savings_year1: 80,
        })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByText(/Net Year 1/i)).toBeInTheDocument();
  });

  it("does NOT render confidence bar when confidence is 0", () => {
    render(
      <CheckNowResult
        result={makeDecision({ confidence: 0 })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.queryByText(/Confidence/i)).not.toBeInTheDocument();
  });

  it("renders confidence percentage when confidence > 0", () => {
    render(
      <CheckNowResult
        result={makeDecision({ confidence: 0.85 })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByText("Confidence: 85%")).toBeInTheDocument();
  });

  it("renders without crashing (smoke test)", () => {
    render(<CheckNowResult result={makeDecision()} onDismiss={jest.fn()} />);
    expect(screen.getByTestId("card")).toBeInTheDocument();
  });
});
