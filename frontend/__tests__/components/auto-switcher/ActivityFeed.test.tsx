import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import ActivityFeed from "@/components/auto-switcher/ActivityFeed";

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
  Clock: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-clock" {...p} />
  ),
  Activity: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-activity" {...p} />
  ),
  Eye: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-eye" {...p} />
  ),
  ThumbsUp: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-thumbsup" {...p} />
  ),
  Zap: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-zap" {...p} />
  ),
}));

jest.mock("@/components/ui/card", () => ({
  Card: ({
    children,
    ...rest
  }: {
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <div data-testid="card" {...rest}>
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

jest.mock("@/components/ui/badge", () => ({
  Badge: ({
    children,
    variant,
  }: {
    children: React.ReactNode;
    variant?: string;
    size?: string;
  }) => (
    <span data-testid="badge" data-variant={variant}>
      {children}
    </span>
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

function makeEntry(overrides: Record<string, unknown> = {}) {
  return {
    id: "entry-1",
    decision: "hold",
    executed: false,
    reason: "Rates are competitive.",
    current_plan_name: "Legacy Plan",
    proposed_plan_name: "CheapCo Flex",
    savings_monthly: null,
    savings_annual: null,
    created_at: "2026-05-12T10:00:00Z",
    ...overrides,
  };
}

function renderFeed(activity?: unknown[], isLoading = false) {
  mockUseAgentActivity.mockReturnValue({ isLoading, data: activity });
  return render(<ActivityFeed />);
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe("ActivityFeed — loading", () => {
  it("renders skeletons while loading", () => {
    renderFeed(undefined, true);
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0);
  });

  it("does not render activity-feed card while loading", () => {
    renderFeed(undefined, true);
    expect(screen.queryByTestId("activity-feed")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe("ActivityFeed — empty", () => {
  it("renders the card", () => {
    renderFeed([]);
    expect(screen.getByTestId("activity-feed")).toBeInTheDocument();
  });

  it("shows 'Recent Activity' title", () => {
    renderFeed([]);
    expect(screen.getByTestId("card-title")).toHaveTextContent(
      "Recent Activity",
    );
  });

  it("shows clock icon in empty state", () => {
    renderFeed([]);
    expect(screen.getByTestId("icon-clock")).toBeInTheDocument();
  });

  it("shows empty-state message", () => {
    renderFeed([]);
    expect(
      screen.getByText(/No activity yet\. Run your first check/),
    ).toBeInTheDocument();
  });

  it("does not render any activity entries", () => {
    renderFeed([]);
    expect(screen.queryAllByTestId("activity-entry")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Populated feed
// ---------------------------------------------------------------------------

describe("ActivityFeed — entries", () => {
  it("renders one activity-entry per item", () => {
    renderFeed([
      makeEntry({ id: "e1" }),
      makeEntry({ id: "e2" }),
      makeEntry({ id: "e3" }),
    ]);
    expect(screen.getAllByTestId("activity-entry")).toHaveLength(3);
  });

  it("shows reason text inside each entry", () => {
    renderFeed([makeEntry({ reason: "Switching saves $15/mo." })]);
    expect(screen.getByText("Switching saves $15/mo.")).toBeInTheDocument();
  });

  it("shows 'Hold' badge for hold decision", () => {
    renderFeed([makeEntry({ decision: "hold" })]);
    const badges = screen.getAllByTestId("badge");
    expect(badges[0]).toHaveTextContent("Hold");
  });

  it("shows 'Switched' badge with success variant for switch decision", () => {
    renderFeed([makeEntry({ decision: "switch" })]);
    const badges = screen.getAllByTestId("badge");
    expect(badges[0]).toHaveTextContent("Switched");
    expect(badges[0]).toHaveAttribute("data-variant", "success");
  });

  it("shows 'Recommendation' badge for recommend decision", () => {
    renderFeed([makeEntry({ decision: "recommend" })]);
    expect(screen.getAllByTestId("badge")[0]).toHaveTextContent(
      "Recommendation",
    );
  });

  it("shows 'Monitoring' badge with warning variant for monitor decision", () => {
    renderFeed([makeEntry({ decision: "monitor" })]);
    const badge = screen.getAllByTestId("badge")[0];
    expect(badge).toHaveTextContent("Monitoring");
    expect(badge).toHaveAttribute("data-variant", "warning");
  });

  it("shows 'Executed' badge when entry.executed is true", () => {
    renderFeed([makeEntry({ executed: true })]);
    const badges = screen.getAllByTestId("badge");
    const executedBadge = badges.find((b) => b.textContent === "Executed");
    expect(executedBadge).toBeTruthy();
  });

  it("does not show 'Executed' badge when entry.executed is false", () => {
    renderFeed([makeEntry({ executed: false })]);
    const badges = screen.getAllByTestId("badge");
    const executedBadge = badges.find((b) => b.textContent === "Executed");
    expect(executedBadge).toBeUndefined();
  });

  it("shows current and proposed plan names", () => {
    renderFeed([
      makeEntry({
        current_plan_name: "OldPlan",
        proposed_plan_name: "NewPlan",
      }),
    ]);
    expect(screen.getByText("OldPlan")).toBeInTheDocument();
    expect(screen.getByText("NewPlan")).toBeInTheDocument();
  });

  it("shows ArrowRight icon when both plan names are present", () => {
    renderFeed([
      makeEntry({
        current_plan_name: "OldPlan",
        proposed_plan_name: "NewPlan",
      }),
    ]);
    expect(screen.getByTestId("icon-arrow")).toBeInTheDocument();
  });

  it("hides plan names section when both are null", () => {
    renderFeed([
      makeEntry({ current_plan_name: null, proposed_plan_name: null }),
    ]);
    expect(screen.queryByTestId("icon-arrow")).not.toBeInTheDocument();
  });

  it("shows savings when savings_monthly > 0", () => {
    renderFeed([makeEntry({ savings_monthly: 20 })]);
    expect(screen.getByText(/\$20\.00\/mo/)).toBeInTheDocument();
  });

  it("appends annual savings when savings_annual is set", () => {
    renderFeed([makeEntry({ savings_monthly: 20, savings_annual: 240 })]);
    expect(screen.getByText(/\$240\.00\/yr/)).toBeInTheDocument();
  });

  it("does not show savings line when savings_monthly is null", () => {
    renderFeed([makeEntry({ savings_monthly: null })]);
    expect(screen.queryByText(/\/mo/)).not.toBeInTheDocument();
  });

  it("does not show savings line when savings_monthly is 0", () => {
    renderFeed([makeEntry({ savings_monthly: 0 })]);
    expect(screen.queryByText(/\/mo/)).not.toBeInTheDocument();
  });
});
