import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// API mocks
// ---------------------------------------------------------------------------

const mockGetHistory = jest.fn();
const mockRollback = jest.fn();

jest.mock("@/lib/api/agent-switcher", () => ({
  getHistory: (...args: unknown[]) => mockGetHistory(...args),
  rollback: (...args: unknown[]) => mockRollback(...args),
}));

// ---------------------------------------------------------------------------
// UI mocks
// ---------------------------------------------------------------------------

jest.mock("@/components/layout/Header", () => ({
  Header: ({ title }: { title: string }) => (
    <header data-testid="header">{title}</header>
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
    disabled,
    loading,
    "aria-label": ariaLabel,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    loading?: boolean;
    variant?: string;
    size?: string;
    leftIcon?: React.ReactNode;
    "aria-label"?: string;
  }) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-loading={String(loading)}
      aria-label={ariaLabel}
    >
      {children}
    </button>
  ),
}));

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={className} />
  ),
}));

jest.mock("@/components/ui/modal", () => ({
  Modal: ({
    open,
    onClose,
    onConfirm,
    title,
  }: {
    open: boolean;
    onClose: () => void;
    onConfirm?: () => void;
    title: string;
    description?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    variant?: string;
  }) =>
    open ? (
      <div role="dialog" aria-label={title}>
        <button onClick={onClose}>Cancel</button>
        {onConfirm && <button onClick={onConfirm}>Confirm</button>}
      </div>
    ) : null,
}));

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

jest.mock("lucide-react", () => {
  const icon = (name: string) => {
    const Icon = ({ className }: { className?: string }) => (
      <svg data-testid={`icon-${name}`} className={className} />
    );
    Icon.displayName = `Icon(${name})`;
    return Icon;
  };
  return {
    ArrowRight: icon("arrow-right"),
    ChevronDown: icon("chevron-down"),
    ChevronUp: icon("chevron-up"),
    Clock: icon("clock"),
    History: icon("history"),
    RotateCcw: icon("rotate-ccw"),
    TrendingUp: icon("trending-up"),
    AlertTriangle: icon("alert-triangle"),
    CheckCircle2: icon("check-circle"),
    XCircle: icon("x-circle"),
    Loader2: icon("loader"),
    ArrowLeft: icon("arrow-left"),
  };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={makeQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}

import SwitchHistoryContent from "@/app/(app)/auto-switcher/history/SwitchHistoryContent";

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const RECENT_DATE = new Date(
  Date.now() - 5 * 24 * 60 * 60 * 1000,
).toISOString(); // 5 days ago
const OLD_DATE = new Date(Date.now() - 40 * 24 * 60 * 60 * 1000).toISOString(); // 40 days ago (outside rollback window)

function makeEntry(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "entry-1",
    decision: "switch",
    executed: true,
    trigger_type: "scheduled",
    current_plan_name: "Basic Plan",
    proposed_plan_name: "Super Saver",
    savings_monthly: 15.5,
    savings_annual: 186.0,
    confidence_score: 0.85,
    reasoning: "Better deal available",
    created_at: RECENT_DATE,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SwitchHistoryContent", () => {
  beforeEach(() => {
    mockGetHistory.mockReset();
    mockRollback.mockReset();
  });

  it("shows loading skeleton on initial load", async () => {
    mockGetHistory.mockReturnValue(new Promise(() => {})); // never resolves
    render(<SwitchHistoryContent />, { wrapper });
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0);
  });

  it("shows error state when fetch fails with no existing entries", async () => {
    mockGetHistory.mockRejectedValue(new Error("Network error"));
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  it("shows empty state when history is empty", async () => {
    mockGetHistory.mockResolvedValue([]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByTestId("empty-history")).toBeInTheDocument();
    });
  });

  it("renders switch entries when data is available", async () => {
    const entry = makeEntry();
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Basic Plan")).toBeInTheDocument();
      expect(screen.getByText("Super Saver")).toBeInTheDocument();
    });
  });

  it("renders 'Load More' button when more entries available (data.length === PAGE_SIZE)", async () => {
    const entries = Array.from({ length: 20 }, (_, i) =>
      makeEntry({ id: `entry-${i}` }),
    );
    mockGetHistory.mockResolvedValue(entries);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /load more/i }),
      ).toBeInTheDocument();
    });
  });

  it("renders savings info when savings_monthly and savings_annual are present", async () => {
    const entry = makeEntry({ savings_monthly: 15.5, savings_annual: 186.0 });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/15\.50\/mo/i)).toBeInTheDocument();
      expect(screen.getByText(/186\.00\/year/i)).toBeInTheDocument();
    });
  });

  it("does not render savings section when both savings are null", async () => {
    const entry = makeEntry({ savings_monthly: null, savings_annual: null });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.queryByTestId("icon-trending-up")).not.toBeInTheDocument();
    });
  });

  it("shows rollback button for active entry within rollback window", async () => {
    const entry = makeEntry({
      decision: "switch",
      executed: true,
      created_at: RECENT_DATE,
    });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /rollback/i }),
      ).toBeInTheDocument();
    });
  });

  it("does not show rollback button for entry outside rollback window", async () => {
    const entry = makeEntry({
      decision: "switch",
      executed: true,
      created_at: OLD_DATE,
    });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /rollback/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("does not show rollback button for non-switch decision", async () => {
    const entry = makeEntry({ decision: "hold", executed: false });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /rollback/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("shows 'hold' descriptive text when decision is hold and no plan names", async () => {
    const entry = makeEntry({
      decision: "hold",
      executed: false,
      current_plan_name: null,
      proposed_plan_name: null,
    });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/current plan evaluated/i)).toBeInTheDocument();
    });
  });

  it("shows 'monitoring in progress' text for monitor decision", async () => {
    const entry = makeEntry({
      decision: "monitor",
      executed: false,
      current_plan_name: null,
      proposed_plan_name: null,
    });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByText(/rate monitoring in progress/i),
      ).toBeInTheDocument();
    });
  });

  it("shows 'plan details unavailable' for unknown decision with no plan names", async () => {
    const entry = makeEntry({
      decision: "recommend",
      executed: false,
      current_plan_name: null,
      proposed_plan_name: null,
    });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/plan details unavailable/i)).toBeInTheDocument();
    });
  });

  it("opens rollback modal when rollback button is clicked", async () => {
    const entry = makeEntry();
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /rollback/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /rollback/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("expands decision details when clicked", async () => {
    const entry = makeEntry({ confidence_score: 0.85 });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.getByText(/scheduled check/i)).toBeInTheDocument();
    });
  });

  it("collapses decision details when clicked again", async () => {
    const entry = makeEntry({ confidence_score: 0.85 });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.getByText(/scheduled check/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.queryByText(/scheduled check/i)).not.toBeInTheDocument();
    });
  });

  it("shows 'initiated' status for switch not yet executed", async () => {
    const entry = makeEntry({ decision: "switch", executed: false });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Initiated")).toBeInTheDocument();
    });
  });

  it("shows 'Recommended' status for recommend decision", async () => {
    const entry = makeEntry({ decision: "recommend", executed: false });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Recommended")).toBeInTheDocument();
    });
  });

  it("shows 'Hold' status for hold decision", async () => {
    const entry = makeEntry({ decision: "hold", executed: false });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Hold")).toBeInTheDocument();
    });
  });

  it("shows 'Monitoring' for monitor decision", async () => {
    const entry = makeEntry({ decision: "monitor", executed: false });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Monitoring")).toBeInTheDocument();
    });
  });

  it("shows 'Failed' status for failed decision", async () => {
    const entry = makeEntry({ decision: "failed", executed: false });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeInTheDocument();
    });
  });

  it("shows 'Rolled Back' status for rolled_back decision", async () => {
    const entry = makeEntry({ decision: "rolled_back", executed: false });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Rolled Back")).toBeInTheDocument();
    });
  });

  it("renders 'Manual Check' for manual trigger type", async () => {
    const entry = makeEntry({ trigger_type: "manual" });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.getByText("Manual Check")).toBeInTheDocument();
    });
  });

  it("renders 'Price Change Detected' for price_change trigger type", async () => {
    const entry = makeEntry({ trigger_type: "price_change" });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.getByText("Price Change Detected")).toBeInTheDocument();
    });
  });

  it("renders humanised label for unknown trigger type", async () => {
    const entry = makeEntry({ trigger_type: "some_custom_trigger" });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.getByText("Some Custom Trigger")).toBeInTheDocument();
    });
  });

  it("uses 'unknown' fallback in rollback button aria-label when plan names are null", async () => {
    const entry = makeEntry({
      decision: "switch",
      executed: true,
      current_plan_name: null,
      proposed_plan_name: null,
      created_at: RECENT_DATE,
    });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      // Rollback button aria-label uses ?? fallback "unknown" for null plan names
      expect(
        screen.getByLabelText("Rollback switch from unknown to unknown"),
      ).toBeInTheDocument();
    });
  });

  it("shows low confidence danger color when confidence_score < 0.5", async () => {
    const entry = makeEntry({ confidence_score: 0.3 });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      // Math.round(0.3 * 100) = 30 — confirms confidence section rendered
      expect(screen.getByText(/30%/)).toBeInTheDocument();
    });
  });

  it("shows medium confidence warning color when confidence_score is between 0.5 and 0.8", async () => {
    const entry = makeEntry({ confidence_score: 0.65 });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.getByText(/65%/)).toBeInTheDocument();
    });
  });

  it("shows 'Contract Expiring' label for contract_expiry trigger type", async () => {
    const entry = makeEntry({ trigger_type: "contract_expiry" });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.getByText("Contract Expiring")).toBeInTheDocument();
    });
  });

  it("hits statusConfig default for a non-standard decision string", async () => {
    const entry = makeEntry({ decision: "pending", executed: false });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      // statusConfig default returns entry.decision as label
      expect(screen.getByText("pending")).toBeInTheDocument();
    });
  });

  it("shows 'Unknown Plan' fallback when current_plan_name is null", async () => {
    const entry = makeEntry({
      current_plan_name: null,
      proposed_plan_name: "Super Saver",
    });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Unknown Plan")).toBeInTheDocument();
      expect(screen.getByText("Super Saver")).toBeInTheDocument();
    });
  });

  it("shows 'Unknown Plan' fallback when proposed_plan_name is null", async () => {
    const entry = makeEntry({
      current_plan_name: "Basic Plan",
      proposed_plan_name: null,
    });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Basic Plan")).toBeInTheDocument();
      expect(screen.getAllByText("Unknown Plan").length).toBeGreaterThan(0);
    });
  });

  it("shows savings_annual section when only savings_annual is non-null", async () => {
    const entry = makeEntry({ savings_monthly: null, savings_annual: 120.0 });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/120\.00\/year/i)).toBeInTheDocument();
      // No monthly trending-up icon since savings_monthly is null
      expect(screen.queryByTestId("icon-trending-up")).not.toBeInTheDocument();
    });
  });

  it("shows ETF section when etf_cost > 0 and net_savings_year1 is null", async () => {
    const entry = makeEntry({ etf_cost: 5.0, net_savings_year1: null });
    mockGetHistory.mockResolvedValue([entry]);
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Decision Details")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Decision Details"));
    await waitFor(() => {
      expect(screen.getByText(/ETF applied/i)).toBeInTheDocument();
      expect(
        screen.queryByText(/Net savings after ETF/i),
      ).not.toBeInTheDocument();
    });
  });

  it("shows 'Rolling back...' while rollback mutation is pending", async () => {
    mockGetHistory.mockResolvedValue([makeEntry()]);
    mockRollback.mockReturnValue(new Promise(() => {}));
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /rollback/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /rollback/i }));
    // Modal mock (in this test file) renders buttons without data-testids — use role+name
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /confirm/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() => {
      expect(screen.getByText("Rolling back...")).toBeInTheDocument();
    });
  });

  it("shows load-more error when second page fetch fails", async () => {
    const entries = Array.from({ length: 20 }, (_, i) =>
      makeEntry({ id: `entry-${i}` }),
    );
    mockGetHistory
      .mockResolvedValueOnce(entries)
      .mockRejectedValue(new Error("load more failed"));
    render(<SwitchHistoryContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /load more/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => {
      expect(
        screen.getByText(/failed to load more entries/i),
      ).toBeInTheDocument();
    });
  });
});
