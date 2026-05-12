import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import PendingRecommendations from "@/components/auto-switcher/PendingRecommendations";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseAgentActivity = jest.fn();

jest.mock("@/lib/hooks/useAutoSwitcher", () => ({
  useAgentActivity: () => mockUseAgentActivity(),
}));

jest.mock("lucide-react", () => ({
  ArrowRight: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-arrow" {...p} />
  ),
  CheckCircle2: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-check" {...p} />
  ),
  DollarSign: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-dollar" {...p} />
  ),
  TrendingDown: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-trend" {...p} />
  ),
}));

jest.mock("@/components/ui/card", () => ({
  Card: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card">{children}</div>
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

jest.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    onClick,
    loading,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    loading?: boolean;
  }) => (
    <button data-testid="approve-button" onClick={onClick} disabled={loading}>
      {children}
    </button>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRec(overrides: Record<string, unknown> = {}) {
  return {
    id: "rec-1",
    decision: "recommend",
    executed: false,
    reason: "CheapCo is 15% cheaper.",
    current_plan_name: "Legacy Plan",
    proposed_plan_name: "CheapCo Flex",
    savings_monthly: 12.5,
    savings_annual: 150,
    confidence_score: 0.87,
    created_at: "2026-05-12T10:00:00Z",
    ...overrides,
  };
}

function renderPending(activity: unknown[] = [], isApproving = false) {
  mockUseAgentActivity.mockReturnValue({ data: activity });
  return render(
    <PendingRecommendations onApprove={jest.fn()} isApproving={isApproving} />,
  );
}

// ---------------------------------------------------------------------------
// Hidden states
// ---------------------------------------------------------------------------

describe("PendingRecommendations — hidden", () => {
  it("renders nothing when activity is empty", () => {
    const { container } = renderPending([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when all activities are executed", () => {
    const { container } = renderPending([makeRec({ executed: true })]);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when no entries have decision=recommend", () => {
    const { container } = renderPending([makeRec({ decision: "hold" })]);
    expect(container).toBeEmptyDOMElement();
  });
});

// ---------------------------------------------------------------------------
// Visible state
// ---------------------------------------------------------------------------

describe("PendingRecommendations — visible", () => {
  it("renders card when pending recommendations exist", () => {
    renderPending([makeRec()]);
    expect(screen.getByTestId("card")).toBeInTheDocument();
  });

  it("shows 'Pending Recommendations' title", () => {
    renderPending([makeRec()]);
    expect(screen.getByTestId("card-title")).toHaveTextContent(
      "Pending Recommendations",
    );
  });

  it("shows count badge matching number of pending items", () => {
    renderPending([makeRec({ id: "r1" }), makeRec({ id: "r2" })]);
    expect(screen.getByTestId("badge")).toHaveTextContent("2");
  });

  it("renders one recommendation-card per pending entry", () => {
    renderPending([
      makeRec({ id: "r1" }),
      makeRec({ id: "r2" }),
      makeRec({ id: "r3" }),
    ]);
    expect(screen.getAllByTestId("recommendation-card")).toHaveLength(3);
  });

  it("filters out executed recommendations", () => {
    renderPending([
      makeRec({ id: "r1", executed: false }),
      makeRec({ id: "r2", executed: true }),
      makeRec({ id: "r3", executed: false }),
    ]);
    expect(screen.getAllByTestId("recommendation-card")).toHaveLength(2);
  });

  it("shows current and proposed plan names", () => {
    renderPending([makeRec()]);
    // Both names are inside the same <span> alongside the ArrowRight icon — use regex
    expect(screen.getByText(/Legacy Plan/)).toBeInTheDocument();
    expect(screen.getByText(/CheapCo Flex/)).toBeInTheDocument();
  });

  it("falls back to 'Current plan' when current_plan_name is null", () => {
    renderPending([makeRec({ current_plan_name: null })]);
    expect(screen.getByText(/Current plan/)).toBeInTheDocument();
  });

  it("falls back to 'Recommended plan' when proposed_plan_name is null", () => {
    renderPending([makeRec({ proposed_plan_name: null })]);
    expect(screen.getByText(/Recommended plan/)).toBeInTheDocument();
  });

  it("shows reason text", () => {
    renderPending([makeRec({ reason: "Switch saves money." })]);
    expect(screen.getByText("Switch saves money.")).toBeInTheDocument();
  });

  it("shows monthly savings when not null", () => {
    renderPending([makeRec({ savings_monthly: 15 })]);
    expect(screen.getByText("$15.00/mo")).toBeInTheDocument();
  });

  it("does not show monthly savings when null", () => {
    renderPending([makeRec({ savings_monthly: null })]);
    expect(screen.queryByText(/\/mo/)).not.toBeInTheDocument();
  });

  it("shows confidence percentage when not null", () => {
    renderPending([makeRec({ confidence_score: 0.92 })]);
    expect(screen.getByText("Confidence: 92%")).toBeInTheDocument();
  });

  it("does not show confidence when null", () => {
    renderPending([makeRec({ confidence_score: null })]);
    expect(screen.queryByText(/Confidence:/)).not.toBeInTheDocument();
  });

  it("renders approve button for each recommendation", () => {
    renderPending([makeRec({ id: "r1" }), makeRec({ id: "r2" })]);
    expect(screen.getAllByTestId("approve-button")).toHaveLength(2);
  });

  it("calls onApprove with correct id when approve is clicked", async () => {
    const onApprove = jest.fn();
    mockUseAgentActivity.mockReturnValue({
      data: [makeRec({ id: "rec-xyz" })],
    });
    render(
      <PendingRecommendations onApprove={onApprove} isApproving={false} />,
    );
    await userEvent.click(screen.getByTestId("approve-button"));
    expect(onApprove).toHaveBeenCalledWith("rec-xyz");
  });

  it("disables approve button while approving", () => {
    renderPending([makeRec()], true);
    expect(screen.getByTestId("approve-button")).toBeDisabled();
  });
});
