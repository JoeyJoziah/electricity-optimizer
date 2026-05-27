import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";

// ---------------------------------------------------------------------------
// Shared analytics fetch mock
// ---------------------------------------------------------------------------

const mockFetchAnalytics = jest.fn();

jest.mock("@/components/connections/analytics/types", () => ({
  fetchAnalytics: (...args: unknown[]) => mockFetchAnalytics(...args),
}));

// ---------------------------------------------------------------------------
// UI mocks (keep tests focused on component logic, not sub-component styles)
// ---------------------------------------------------------------------------

jest.mock("@/components/ui/card", () => ({
  Card: ({
    children,
  }: {
    children: React.ReactNode;
    "data-testid"?: string;
  }) => <div data-testid="card">{children}</div>,
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

jest.mock("@/components/ui/badge", () => ({
  Badge: ({
    children,
    variant,
    className,
  }: {
    children: React.ReactNode;
    variant?: string;
    className?: string;
  }) => (
    <span data-testid="badge" data-variant={variant} className={className}>
      {children}
    </span>
  ),
}));

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

jest.mock("lucide-react", () => {
  const icon = (name: string) => {
    const Icon = ({
      className,
      "aria-hidden": ah,
    }: {
      className?: string;
      "aria-hidden"?: string;
    }) => (
      <svg
        data-testid={`icon-${name}`}
        className={className}
        aria-hidden={ah}
      />
    );
    Icon.displayName = `Icon(${name})`;
    return Icon;
  };
  return {
    DollarSign: icon("dollar-sign"),
    Loader2: icon("loader-2"),
    TrendingUp: icon("trending-up"),
    TrendingDown: icon("trending-down"),
    AlertTriangle: icon("alert-triangle"),
    RefreshCw: icon("refresh-cw"),
    CheckCircle: icon("check-circle"),
    Clock: icon("clock"),
    BarChart3: icon("bar-chart-3"),
  };
});

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import { SavingsEstimateCard } from "@/components/connections/analytics/SavingsEstimateCard";
import { ConnectionHealthCard } from "@/components/connections/analytics/ConnectionHealthCard";
import { RateComparisonCard } from "@/components/connections/analytics/RateComparisonCard";

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function makeSavings(overrides = {}) {
  return {
    estimated_annual_savings_vs_best: 240,
    estimated_monthly_savings_vs_best: 20,
    current_annual_cost: 1800,
    ...overrides,
  };
}

function makeHealth(overrides = {}) {
  return {
    stale_connections: [],
    rate_change_alerts: [],
    ...overrides,
  };
}

function makeComparison(overrides = {}) {
  return {
    user_rate: 0.15,
    market_average: 0.12,
    delta: 0.03,
    percentage_difference: 25.0,
    is_above_average: true,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

// ===========================================================================
// SavingsEstimateCard
// ===========================================================================

describe("SavingsEstimateCard", () => {
  it("shows loading state initially", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<SavingsEstimateCard refreshKey={0} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(/calculating savings/i)).toBeInTheDocument();
  });

  it("shows error state on fetch failure", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("API down"));
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    // Error message should mention the failure
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders savings amount on success", async () => {
    mockFetchAnalytics.mockResolvedValue(makeSavings());
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("annual-savings-amount")).toBeInTheDocument();
    });
    expect(screen.getByTestId("annual-savings-amount")).toHaveTextContent(
      "$240",
    );
  });

  it("clamps negative savings to zero (no negative display)", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeSavings({
        estimated_annual_savings_vs_best: -50,
        estimated_monthly_savings_vs_best: -5,
      }),
    );
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("annual-savings-amount")).toBeInTheDocument();
    });
    // Clamped to 0
    expect(screen.getByTestId("annual-savings-amount")).toHaveTextContent("$0");
  });

  it("shows current annual cost in the comparison section", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeSavings({ current_annual_cost: 2400 }),
    );
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/current annual cost/i)).toBeInTheDocument();
    });
    expect(screen.getByText("$2,400")).toBeInTheDocument();
  });

  it("renders kWh input with default value 900", async () => {
    mockFetchAnalytics.mockResolvedValue(makeSavings());
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByRole("spinbutton")).toBeInTheDocument();
    });
    expect(screen.getByRole("spinbutton")).toHaveValue(900);
  });

  it("updates inputValue immediately on change but debounces monthlyKwh (500ms)", async () => {
    mockFetchAnalytics.mockResolvedValue(makeSavings());
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByRole("spinbutton")).toBeInTheDocument();
    });
    const input = screen.getByRole("spinbutton");
    // Change before debounce fires — fetchAnalytics called only once (initial load)
    fireEvent.change(input, { target: { value: "500" } });
    expect(mockFetchAnalytics).toHaveBeenCalledTimes(1); // debounce not fired yet
    // Advance timer past debounce
    act(() => jest.advanceTimersByTime(500));
    // Now monthlyKwh updates → load() runs → second fetch
    await waitFor(() => {
      expect(mockFetchAnalytics.mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("ignores kWh values <= 0 (does not update monthlyKwh)", async () => {
    mockFetchAnalytics.mockResolvedValue(makeSavings());
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByRole("spinbutton")).toBeInTheDocument();
    });
    const input = screen.getByRole("spinbutton");
    const callsBefore = mockFetchAnalytics.mock.calls.length;
    fireEvent.change(input, { target: { value: "0" } });
    act(() => jest.advanceTimersByTime(600)); // past debounce
    // No additional fetch — invalid value rejected
    expect(mockFetchAnalytics.mock.calls.length).toBe(callsBefore);
  });

  it("ignores kWh values > 99999", async () => {
    mockFetchAnalytics.mockResolvedValue(makeSavings());
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByRole("spinbutton")).toBeInTheDocument();
    });
    const callsBefore = mockFetchAnalytics.mock.calls.length;
    fireEvent.change(screen.getByRole("spinbutton"), {
      target: { value: "100000" },
    });
    act(() => jest.advanceTimersByTime(600));
    expect(mockFetchAnalytics.mock.calls.length).toBe(callsBefore);
  });

  it("retry button re-triggers fetch on error", async () => {
    mockFetchAnalytics
      .mockRejectedValueOnce(new Error("Network error"))
      .mockResolvedValue(makeSavings());
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /retry/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => {
      expect(screen.getByTestId("annual-savings-amount")).toBeInTheDocument();
    });
  });

  it("re-fetches when refreshKey changes", async () => {
    mockFetchAnalytics.mockResolvedValue(makeSavings());
    const { rerender } = render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("annual-savings-amount")).toBeInTheDocument(),
    );
    rerender(<SavingsEstimateCard refreshKey={1} />);
    await waitFor(() => {
      expect(mockFetchAnalytics.mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("renders empty state (not $NaN) for the {has_data:false} no-rate response", async () => {
    // Backend returns this sentinel when the user has a connection but no
    // extracted rate yet — numeric fields are absent.
    mockFetchAnalytics.mockResolvedValue({
      has_data: false,
      message: "No rate data available for savings calculation.",
    });
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("savings-estimate-empty")).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("annual-savings-amount"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/\$NaN/)).not.toBeInTheDocument();
  });

  it("cleans up debounce timer on unmount (no state update after unmount)", async () => {
    mockFetchAnalytics.mockResolvedValue(makeSavings());
    const { unmount } = render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByRole("spinbutton")).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByRole("spinbutton"), {
      target: { value: "300" },
    });
    unmount(); // should cancel timer — no state update warnings
    act(() => jest.advanceTimersByTime(600));
  });
});

// ===========================================================================
// ConnectionHealthCard
// ===========================================================================

describe("ConnectionHealthCard", () => {
  it("shows loading state initially", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<ConnectionHealthCard refreshKey={0} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(/checking health/i)).toBeInTheDocument();
  });

  it("shows error state on fetch failure", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("Network error"));
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("shows all-healthy message when no issues", async () => {
    mockFetchAnalytics.mockResolvedValue(makeHealth());
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(
        screen.getByText(/all connections are healthy/i),
      ).toBeInTheDocument();
    });
    // No issues badge when healthy
    expect(screen.queryByTestId("badge")).not.toBeInTheDocument();
  });

  it("shows issue count badge when stale connections exist", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeHealth({
        stale_connections: [
          {
            connection_id: "conn-1",
            label: "Eversource",
            last_scan_at: null,
            days_since_sync: 5,
          },
        ],
      }),
    );
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("badge")).toBeInTheDocument();
    });
    expect(screen.getByTestId("badge")).toHaveTextContent("1 issue");
  });

  it("renders plural 'issues' for multiple problems", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeHealth({
        stale_connections: [
          {
            connection_id: "c1",
            label: "Eversource",
            last_scan_at: null,
            days_since_sync: 3,
          },
          {
            connection_id: "c2",
            label: "ConEd",
            last_scan_at: null,
            days_since_sync: 7,
          },
        ],
      }),
    );
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("badge")).toHaveTextContent("2 issues");
    });
  });

  it("renders stale connection row with supplier name and days", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeHealth({
        stale_connections: [
          {
            connection_id: "s1",
            label: "PSEG",
            last_scan_at: null,
            days_since_sync: 4,
          },
        ],
      }),
    );
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("stale-connection-s1")).toBeInTheDocument();
    });
    expect(screen.getByText("PSEG")).toBeInTheDocument();
    expect(screen.getByText(/4 days ago/i)).toBeInTheDocument();
  });

  it("uses singular 'day' for 1 day since sync", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeHealth({
        stale_connections: [
          {
            connection_id: "s2",
            label: "NRG",
            last_scan_at: null,
            days_since_sync: 1,
          },
        ],
      }),
    );
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/1 day ago/i)).toBeInTheDocument();
    });
  });

  it("renders Sync Now button for stale connections when onSync provided", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeHealth({
        stale_connections: [
          {
            connection_id: "s3",
            label: "Unitil",
            last_scan_at: null,
            days_since_sync: 6,
          },
        ],
      }),
    );
    const onSync = jest.fn().mockResolvedValue(undefined);
    render(<ConnectionHealthCard refreshKey={0} onSync={onSync} />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /sync unitil/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /sync unitil/i }));
    expect(onSync).toHaveBeenCalledWith("s3");
  });

  it("does not render Sync Now button when onSync not provided", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeHealth({
        stale_connections: [
          {
            connection_id: "s4",
            label: "CL&P",
            last_scan_at: null,
            days_since_sync: 3,
          },
        ],
      }),
    );
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("stale-connection-s4")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /sync/i }),
    ).not.toBeInTheDocument();
  });

  it("renders rate increase alert with danger styling indicator", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeHealth({
        rate_change_alerts: [
          {
            connection_id: "a1",
            supplier: "Eversource",
            previous_rate: 0.1,
            current_rate: 0.14,
            change_percentage: 40.0,
            detected_at: "2026-05-10T00:00:00Z",
          },
        ],
      }),
    );
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("rate-alert-a1")).toBeInTheDocument();
    });
    expect(screen.getByText(/rate increased/i)).toBeInTheDocument();
    // Badge should show + percentage (may be multiple badges; find the one in the alert)
    const alert = screen.getByTestId("rate-alert-a1");
    expect(alert.querySelector('[data-testid="badge"]')).toHaveTextContent(
      "+40.0%",
    );
  });

  it("renders rate decrease alert with success indicator", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeHealth({
        rate_change_alerts: [
          {
            connection_id: "a2",
            supplier: "ConEd",
            previous_rate: 0.14,
            current_rate: 0.11,
            change_percentage: -21.4,
            detected_at: "2026-05-10T00:00:00Z",
          },
        ],
      }),
    );
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/rate decreased/i)).toBeInTheDocument();
    });
  });

  it("retry button re-triggers fetch on error", async () => {
    mockFetchAnalytics
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValue(makeHealth());
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /retry/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => {
      expect(
        screen.getByText(/all connections are healthy/i),
      ).toBeInTheDocument();
    });
  });
});

// ===========================================================================
// RateComparisonCard
// ===========================================================================

describe("RateComparisonCard", () => {
  it("shows loading state initially", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<RateComparisonCard refreshKey={0} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(/loading comparison/i)).toBeInTheDocument();
  });

  it("shows error state on fetch failure", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("fail"));
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("renders user rate and market average on success", async () => {
    mockFetchAnalytics.mockResolvedValue(makeComparison());
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => {
      // 0.15 * 100 = 15.00 c/kWh
      expect(screen.getByText("15.00")).toBeInTheDocument();
      // 0.12 * 100 = 12.00 c/kWh
      expect(screen.getByText("12.00")).toBeInTheDocument();
    });
  });

  it("shows 'Above market average' when is_above_average=true", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeComparison({ is_above_average: true }),
    );
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/above market average/i)).toBeInTheDocument();
    });
  });

  it("shows 'Below market average' when is_above_average=false", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeComparison({ is_above_average: false, percentage_difference: 8.5 }),
    );
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/below market average/i)).toBeInTheDocument();
    });
  });

  it("shows percentage difference in badge", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeComparison({ is_above_average: true, percentage_difference: 25.0 }),
    );
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("badge")).toHaveTextContent("+25.0%");
    });
  });

  it("shows no + prefix for below-average percentage", async () => {
    mockFetchAnalytics.mockResolvedValue(
      makeComparison({ is_above_average: false, percentage_difference: -10.0 }),
    );
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => {
      const badge = screen.getByTestId("badge");
      expect(badge.textContent).not.toContain("+");
    });
  });

  it("retry button re-triggers fetch on error", async () => {
    mockFetchAnalytics
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValue(makeComparison());
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /retry/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => {
      expect(screen.getByText(/above market average/i)).toBeInTheDocument();
    });
  });

  it("re-fetches when refreshKey changes", async () => {
    mockFetchAnalytics.mockResolvedValue(makeComparison());
    const { rerender } = render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText(/above market average/i)).toBeInTheDocument(),
    );
    rerender(<RateComparisonCard refreshKey={2} />);
    await waitFor(() => {
      expect(mockFetchAnalytics.mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("renders empty state (does not crash on .toFixed) for {has_data:false} response", async () => {
    // Regression: backend returns this sentinel when the user has a connection
    // but no extracted rate yet. percentage_difference is absent — the card must
    // not call undefined.toFixed() (which previously crashed the /connections route).
    mockFetchAnalytics.mockResolvedValue({
      has_data: false,
      message:
        "No extracted rates found. Connect a utility account to see comparisons.",
    });
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("rate-comparison-empty")).toBeInTheDocument();
    });
    // No badge / percentage rendered, no crash
    expect(screen.queryByTestId("badge")).not.toBeInTheDocument();
    expect(screen.getByText(/no extracted rates found/i)).toBeInTheDocument();
  });
});
