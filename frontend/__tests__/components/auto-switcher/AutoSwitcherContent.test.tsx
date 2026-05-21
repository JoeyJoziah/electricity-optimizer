import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mock mutation hooks
// ---------------------------------------------------------------------------

const mockCheckNow = jest.fn();
const mockApproveSwitch = jest.fn();
const mockRollback = jest.fn();

jest.mock("@/lib/hooks/useAutoSwitcher", () => ({
  useCheckNow: () => mockCheckNow(),
  useApproveSwitch: () => mockApproveSwitch(),
  useRollback: () => mockRollback(),
}));

// ---------------------------------------------------------------------------
// Mock child components so we can test composition in isolation
// ---------------------------------------------------------------------------

jest.mock("@/components/layout/Header", () => ({
  Header: ({ title }: { title: string }) => (
    <header data-testid="header">{title}</header>
  ),
}));

jest.mock("@/components/auto-switcher/ActivityFeed", () => ({
  __esModule: true,
  default: () => <div data-testid="activity-feed-stub" />,
}));

jest.mock("@/components/auto-switcher/AgentStatusCard", () => ({
  __esModule: true,
  default: ({
    onCheckNow,
    isChecking,
  }: {
    onCheckNow: () => void;
    isChecking: boolean;
  }) => (
    <div
      data-testid="agent-status-card-stub"
      data-checking={String(isChecking)}
    >
      <button onClick={onCheckNow} data-testid="check-now-trigger">
        Check Now
      </button>
    </div>
  ),
}));

jest.mock("@/components/auto-switcher/CheckNowResult", () => ({
  __esModule: true,
  default: ({
    result,
    onDismiss,
  }: {
    result: { action: string };
    onDismiss: () => void;
  }) => (
    <div data-testid="check-now-result-stub" data-action={result.action}>
      <button onClick={onDismiss} data-testid="dismiss-result">
        Dismiss
      </button>
    </div>
  ),
}));

jest.mock("@/components/auto-switcher/CurrentPlanCard", () => ({
  __esModule: true,
  default: ({ isLoading }: { isLoading: boolean }) => (
    <div
      data-testid="current-plan-card-stub"
      data-loading={String(isLoading)}
    />
  ),
}));

jest.mock("@/components/auto-switcher/PendingRecommendations", () => ({
  __esModule: true,
  default: ({
    onApprove,
    isApproving,
  }: {
    onApprove: (id: string) => void;
    isApproving: boolean;
  }) => (
    <div
      data-testid="pending-recommendations-stub"
      data-approving={String(isApproving)}
    >
      <button
        onClick={() => onApprove("audit-123")}
        data-testid="approve-trigger"
      >
        Approve
      </button>
    </div>
  ),
}));

jest.mock("@/components/auto-switcher/ProtectedBanner", () => ({
  __esModule: true,
  default: ({
    onRollback,
    isRollingBack,
  }: {
    onRollback: (id: string) => void;
    isRollingBack: boolean;
  }) => (
    <div
      data-testid="protected-banner-stub"
      data-rolling-back={String(isRollingBack)}
    >
      <button
        onClick={() => onRollback("exec-456")}
        data-testid="rollback-trigger"
      >
        Rollback
      </button>
    </div>
  ),
}));

import AutoSwitcherContent from "@/components/auto-switcher/AutoSwitcherContent";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMutation(overrides: Record<string, unknown> = {}) {
  return {
    mutate: jest.fn(),
    isPending: false,
    isError: false,
    ...overrides,
  };
}

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestWrapper";
  return Wrapper;
}

function setup(
  checkOverrides = {},
  approveOverrides = {},
  rollbackOverrides = {},
) {
  mockCheckNow.mockReturnValue(makeMutation(checkOverrides));
  mockApproveSwitch.mockReturnValue(makeMutation(approveOverrides));
  mockRollback.mockReturnValue(makeMutation(rollbackOverrides));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AutoSwitcherContent", () => {
  beforeEach(() => {
    mockCheckNow.mockReset();
    mockApproveSwitch.mockReset();
    mockRollback.mockReset();
  });

  it("renders the Auto Switcher header", () => {
    setup();
    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("header")).toHaveTextContent("Auto Switcher");
  });

  it("renders all child component stubs", () => {
    setup();
    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("agent-status-card-stub")).toBeInTheDocument();
    expect(screen.getByTestId("current-plan-card-stub")).toBeInTheDocument();
    expect(
      screen.getByTestId("pending-recommendations-stub"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("protected-banner-stub")).toBeInTheDocument();
    expect(screen.getByTestId("activity-feed-stub")).toBeInTheDocument();
  });

  it("does not render CheckNowResult when checkResult is null", () => {
    setup();
    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    expect(
      screen.queryByTestId("check-now-result-stub"),
    ).not.toBeInTheDocument();
  });

  it("renders CheckNowResult when check-now mutation succeeds", () => {
    const decision = { action: "hold", reason: "Rates competitive" };
    mockCheckNow.mockReturnValue({
      ...makeMutation(),
      mutate: jest.fn().mockImplementation((_vars, opts) => {
        opts.onSuccess(decision);
      }),
    });
    mockApproveSwitch.mockReturnValue(makeMutation());
    mockRollback.mockReturnValue(makeMutation());

    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("check-now-trigger"));
    expect(screen.getByTestId("check-now-result-stub")).toBeInTheDocument();
    expect(screen.getByTestId("check-now-result-stub")).toHaveAttribute(
      "data-action",
      "hold",
    );
  });

  it("dismisses CheckNowResult when Dismiss is clicked", () => {
    const decision = { action: "switch", reason: "Better rate" };
    mockCheckNow.mockReturnValue({
      ...makeMutation(),
      mutate: jest.fn().mockImplementation((_vars, opts) => {
        opts.onSuccess(decision);
      }),
    });
    mockApproveSwitch.mockReturnValue(makeMutation());
    mockRollback.mockReturnValue(makeMutation());

    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("check-now-trigger"));
    expect(screen.getByTestId("check-now-result-stub")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("dismiss-result"));
    expect(
      screen.queryByTestId("check-now-result-stub"),
    ).not.toBeInTheDocument();
  });

  it("shows check error banner when checkMutation.isError", () => {
    setup({ isError: true });
    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    expect(screen.getByText(/failed to run evaluation/i)).toBeInTheDocument();
  });

  it("shows approve error banner when approveMutation.isError", () => {
    setup({}, { isError: true });
    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    expect(
      screen.getByText(/failed to approve recommendation/i),
    ).toBeInTheDocument();
  });

  it("shows rollback error banner when rollbackMutation.isError", () => {
    setup({}, {}, { isError: true });
    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    expect(screen.getByText(/failed to rollback switch/i)).toBeInTheDocument();
  });

  it("passes isPending to AgentStatusCard as isChecking", () => {
    setup({ isPending: true });
    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("agent-status-card-stub")).toHaveAttribute(
      "data-checking",
      "true",
    );
  });

  it("calls approveMutation.mutate when approve is triggered", () => {
    const approveMutate = jest.fn();
    mockCheckNow.mockReturnValue(makeMutation());
    mockApproveSwitch.mockReturnValue({
      ...makeMutation(),
      mutate: approveMutate,
    });
    mockRollback.mockReturnValue(makeMutation());

    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("approve-trigger"));
    expect(approveMutate).toHaveBeenCalledWith("audit-123");
  });

  it("calls rollbackMutation.mutate when rollback is triggered", () => {
    const rollbackMutate = jest.fn();
    mockCheckNow.mockReturnValue(makeMutation());
    mockApproveSwitch.mockReturnValue(makeMutation());
    mockRollback.mockReturnValue({ ...makeMutation(), mutate: rollbackMutate });

    render(<AutoSwitcherContent />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("rollback-trigger"));
    expect(rollbackMutate).toHaveBeenCalledWith("exec-456");
  });
});
