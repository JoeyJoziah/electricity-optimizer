import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import AgentStatusCard from "@/components/auto-switcher/AgentStatusCard";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseAgentSettings = jest.fn();
const mockUseAgentActivity = jest.fn();

jest.mock("@/lib/hooks/useAutoSwitcher", () => ({
  useAgentSettings: () => mockUseAgentSettings(),
  useAgentActivity: () => mockUseAgentActivity(),
}));

jest.mock("lucide-react", () => ({
  RefreshCw: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-refresh" {...p} />
  ),
  ToggleLeft: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-toggle-off" {...p} />
  ),
  ToggleRight: (p: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-toggle-on" {...p} />
  ),
}));

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

jest.mock("@/components/ui/card", () => ({
  Card: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card">{children}</div>
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
    <button data-testid="check-now-button" onClick={onClick} disabled={loading}>
      {children}
    </button>
  ),
}));

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={className} />
  ),
}));

// decisionPresentation is a real module — no mock needed

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSettings(overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    paused_until: null,
    loa_signed: false,
    ...overrides,
  };
}

function renderCard(
  settingsOverrides: Record<string, unknown> = {},
  activity: unknown[] = [],
  isLoading = false,
) {
  mockUseAgentSettings.mockReturnValue({
    isLoading,
    data: isLoading ? undefined : makeSettings(settingsOverrides),
  });
  mockUseAgentActivity.mockReturnValue({ data: activity });

  return render(<AgentStatusCard onCheckNow={jest.fn()} isChecking={false} />);
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe("AgentStatusCard — loading", () => {
  it("renders skeletons while settings are loading", () => {
    renderCard({}, [], true);
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0);
  });

  it("does not render badge while loading", () => {
    renderCard({}, [], true);
    expect(screen.queryByTestId("badge")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Status badge variants
// ---------------------------------------------------------------------------

describe("AgentStatusCard — status badges", () => {
  it("shows 'Disabled' with danger variant when disabled", () => {
    renderCard({ enabled: false });
    expect(screen.getByTestId("badge")).toHaveTextContent("Disabled");
    expect(screen.getByTestId("badge")).toHaveAttribute(
      "data-variant",
      "danger",
    );
  });

  it("shows 'Active (Manual)' with success variant when enabled, not paused, loa not signed", () => {
    renderCard({ enabled: true, paused_until: null, loa_signed: false });
    expect(screen.getByTestId("badge")).toHaveTextContent("Active (Manual)");
    expect(screen.getByTestId("badge")).toHaveAttribute(
      "data-variant",
      "success",
    );
  });

  it("shows 'Active (Auto)' when enabled and loa_signed", () => {
    renderCard({ enabled: true, paused_until: null, loa_signed: true });
    expect(screen.getByTestId("badge")).toHaveTextContent("Active (Auto)");
  });

  it("shows 'Paused' with warning variant when enabled but paused", () => {
    renderCard({
      enabled: true,
      paused_until: "2026-06-01T00:00:00Z",
      loa_signed: false,
    });
    expect(screen.getByTestId("badge")).toHaveTextContent("Paused");
    expect(screen.getByTestId("badge")).toHaveAttribute(
      "data-variant",
      "warning",
    );
  });
});

// ---------------------------------------------------------------------------
// Activity / last scan
// ---------------------------------------------------------------------------

describe("AgentStatusCard — last scan", () => {
  it("shows 'No scans yet' when activity is empty", () => {
    renderCard({}, []);
    expect(screen.getByText("No scans yet")).toBeInTheDocument();
  });

  it("shows last scan date when activity has entries", () => {
    renderCard({}, [
      {
        id: "a1",
        created_at: "2026-05-12T10:00:00Z",
        decision: "hold",
        executed: false,
      },
    ]);
    expect(screen.queryByText("No scans yet")).not.toBeInTheDocument();
  });

  it("shows last scan decision inline", () => {
    renderCard({}, [
      {
        id: "a1",
        created_at: "2026-05-12T10:00:00Z",
        decision: "switch",
        executed: true,
      },
    ]);
    expect(screen.getByText("switch")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Check Now button
// ---------------------------------------------------------------------------

describe("AgentStatusCard — check now button", () => {
  it("calls onCheckNow when button is clicked", async () => {
    const onCheckNow = jest.fn();
    mockUseAgentSettings.mockReturnValue({
      isLoading: false,
      data: makeSettings(),
    });
    mockUseAgentActivity.mockReturnValue({ data: [] });

    render(<AgentStatusCard onCheckNow={onCheckNow} isChecking={false} />);
    await userEvent.click(screen.getByTestId("check-now-button"));
    expect(onCheckNow).toHaveBeenCalledTimes(1);
  });

  it("button is disabled while checking", () => {
    mockUseAgentSettings.mockReturnValue({
      isLoading: false,
      data: makeSettings(),
    });
    mockUseAgentActivity.mockReturnValue({ data: [] });

    render(<AgentStatusCard onCheckNow={jest.fn()} isChecking={true} />);
    expect(screen.getByTestId("check-now-button")).toBeDisabled();
  });
});
