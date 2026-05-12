import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import ProtectedBanner from "@/components/auto-switcher/ProtectedBanner";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseAgentActivity = jest.fn();

jest.mock("@/lib/hooks/useAutoSwitcher", () => ({
  useAgentActivity: () => mockUseAgentActivity(),
}));

jest.mock("lucide-react", () => ({
  Shield: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-shield" {...p} />
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
    <button data-testid="rollback-button" onClick={onClick} disabled={loading}>
      {children}
    </button>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeActivity(overrides: Record<string, unknown> = {}) {
  return {
    id: "exec-1",
    decision: "switch",
    executed: true,
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2h ago
    proposed_plan_name: "GreenRate Flex",
    ...overrides,
  };
}

function renderBanner(activity: unknown[] = [], isRollingBack = false) {
  mockUseAgentActivity.mockReturnValue({ data: activity });
  return render(
    <ProtectedBanner onRollback={jest.fn()} isRollingBack={isRollingBack} />,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ProtectedBanner — hidden states", () => {
  it("renders nothing when activity is empty", () => {
    const { container } = renderBanner([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when no 'switch' entries in activity", () => {
    const { container } = renderBanner([
      makeActivity({ decision: "hold", executed: false }),
    ]);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when switch is older than 72 hours", () => {
    const old = new Date(Date.now() - 73 * 60 * 60 * 1000).toISOString();
    const { container } = renderBanner([makeActivity({ created_at: old })]);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when switch entry is not executed", () => {
    const { container } = renderBanner([
      makeActivity({ decision: "switch", executed: false }),
    ]);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ProtectedBanner — visible state", () => {
  it("renders banner when recent executed switch exists", () => {
    renderBanner([makeActivity()]);
    expect(screen.getByTestId("card")).toBeInTheDocument();
  });

  it("shows shield icon", () => {
    renderBanner([makeActivity()]);
    expect(screen.getByTestId("icon-shield")).toBeInTheDocument();
  });

  it("shows 'Your switch is protected' heading", () => {
    renderBanner([makeActivity()]);
    expect(screen.getByText("Your switch is protected")).toBeInTheDocument();
  });

  it("shows the proposed plan name", () => {
    renderBanner([makeActivity({ proposed_plan_name: "CleanEnergy Plus" })]);
    expect(screen.getByText("CleanEnergy Plus")).toBeInTheDocument();
  });

  it("falls back to 'a new plan' when proposed_plan_name is null", () => {
    renderBanner([makeActivity({ proposed_plan_name: null })]);
    expect(screen.getByText("a new plan")).toBeInTheDocument();
  });

  it("shows hours remaining (approximately correct for recent switch)", () => {
    // 2h ago → ~70h remaining
    renderBanner([makeActivity()]);
    expect(screen.getByText(/\d+h/)).toBeInTheDocument();
    const hoursText = screen.getByText(/\d+h/).textContent!;
    const hours = parseInt(hoursText);
    expect(hours).toBeGreaterThan(60);
    expect(hours).toBeLessThanOrEqual(72);
  });

  it("renders rollback button", () => {
    renderBanner([makeActivity()]);
    expect(screen.getByTestId("rollback-button")).toBeInTheDocument();
    expect(screen.getByTestId("rollback-button")).toHaveTextContent(
      "Rollback Switch",
    );
  });

  it("disables rollback button while rolling back", () => {
    mockUseAgentActivity.mockReturnValue({ data: [makeActivity()] });
    render(<ProtectedBanner onRollback={jest.fn()} isRollingBack={true} />);
    expect(screen.getByTestId("rollback-button")).toBeDisabled();
  });

  it("calls onRollback with the execution id when rollback is clicked", async () => {
    const onRollback = jest.fn();
    mockUseAgentActivity.mockReturnValue({
      data: [makeActivity({ id: "exec-xyz" })],
    });
    render(<ProtectedBanner onRollback={onRollback} isRollingBack={false} />);
    await userEvent.click(screen.getByTestId("rollback-button"));
    expect(onRollback).toHaveBeenCalledWith("exec-xyz");
  });
});
