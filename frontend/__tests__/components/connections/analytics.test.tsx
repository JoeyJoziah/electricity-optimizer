import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

// ---------------------------------------------------------------------------
// Mock fetchAnalytics and formatDate from the shared types module
// ---------------------------------------------------------------------------

const mockFetchAnalytics = jest.fn();

jest.mock("@/components/connections/analytics/types", () => ({
  ...jest.requireActual("@/components/connections/analytics/types"),
  fetchAnalytics: (...args: unknown[]) => mockFetchAnalytics(...args),
}));

import { RateComparisonCard } from "@/components/connections/analytics/RateComparisonCard";
import { ConnectionHealthCard } from "@/components/connections/analytics/ConnectionHealthCard";
import { SavingsEstimateCard } from "@/components/connections/analytics/SavingsEstimateCard";
import { RateHistoryCard } from "@/components/connections/analytics/RateHistoryCard";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const _comparison = {
  user_rate: 0.14,
  market_average: 0.12,
  delta: 0.02,
  percentage_difference: 16.7,
  is_above_average: true,
};

const _comparisonBelow = {
  ..._comparison,
  user_rate: 0.1,
  delta: -0.02,
  percentage_difference: -16.7,
  is_above_average: false,
};

const _savings = {
  estimated_annual_savings_vs_best: 240,
  estimated_monthly_savings_vs_best: 20,
  current_annual_cost: 1680,
};

const _health = {
  stale_connections: [
    {
      id: "conn-1",
      supplier_name: "GreenPower",
      last_sync_at: "2026-04-01T00:00:00Z",
      days_since_sync: 41,
    },
  ],
  rate_change_alerts: [
    {
      id: "alert-1",
      supplier_name: "BlueSky",
      old_rate: 0.1,
      new_rate: 0.12,
      change_percentage: 20.0,
      detected_at: "2026-05-10T00:00:00Z",
    },
  ],
};

const _history = {
  data_points: [
    { date: "2026-05-12", rate: 0.14, supplier: "GreenPower" },
    { date: "2026-05-11", rate: 0.13, supplier: "GreenPower" },
    { date: "2026-05-10", rate: 0.13, supplier: "GreenPower" },
  ],
};

// ---------------------------------------------------------------------------
// RateComparisonCard
// ---------------------------------------------------------------------------

describe("RateComparisonCard", () => {
  beforeEach(() => mockFetchAnalytics.mockReset());

  it("shows loading state on mount", () => {
    // Never-resolving promise to stay in loading state
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<RateComparisonCard refreshKey={0} />);
    expect(screen.getByTestId("rate-comparison-loading")).toBeInTheDocument();
  });

  it("renders populated data after fetch resolves", async () => {
    mockFetchAnalytics.mockResolvedValue(_comparison);
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("rate-comparison-card")).toBeInTheDocument(),
    );
    // user_rate * 100 = 14.00 c/kWh
    expect(screen.getByText(/14\.00/)).toBeInTheDocument();
    expect(screen.getByText(/12\.00/)).toBeInTheDocument();
  });

  it("shows Above market average when is_above_average=true", async () => {
    mockFetchAnalytics.mockResolvedValue(_comparison);
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText("Above market average")).toBeInTheDocument(),
    );
  });

  it("shows Below market average when is_above_average=false", async () => {
    mockFetchAnalytics.mockResolvedValue(_comparisonBelow);
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText("Below market average")).toBeInTheDocument(),
    );
  });

  it("shows percentage_difference badge", async () => {
    mockFetchAnalytics.mockResolvedValue(_comparison);
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText(/\+16\.7%/)).toBeInTheDocument(),
    );
  });

  it("shows error state and retry button on fetch failure", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("Network failure"));
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /retry loading rate comparison/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("Network failure")).toBeInTheDocument();
  });

  it("retries load when retry button is clicked", async () => {
    mockFetchAnalytics
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValue(_comparison);
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /retry/i }),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() =>
      expect(screen.getByText("Above market average")).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// SavingsEstimateCard
// ---------------------------------------------------------------------------

describe("SavingsEstimateCard", () => {
  beforeEach(() => mockFetchAnalytics.mockReset());

  it("shows loading state on mount", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<SavingsEstimateCard refreshKey={0} />);
    expect(screen.getByTestId("savings-estimate-loading")).toBeInTheDocument();
  });

  it("renders annual savings amount after load", async () => {
    mockFetchAnalytics.mockResolvedValue(_savings);
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("annual-savings-amount")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("annual-savings-amount")).toHaveTextContent(
      "$240",
    );
  });

  it("renders monthly savings comparison line", async () => {
    mockFetchAnalytics.mockResolvedValue(_savings);
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText(/\$20\/month/i)).toBeInTheDocument(),
    );
  });

  it("renders current annual cost", async () => {
    mockFetchAnalytics.mockResolvedValue(_savings);
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText(/Current annual cost/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("$1,680")).toBeInTheDocument();
  });

  it("renders monthly kWh usage input with default 900", async () => {
    mockFetchAnalytics.mockResolvedValue(_savings);
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(
        screen.getByLabelText(/monthly electricity usage/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/monthly electricity usage/i)).toHaveValue(
      900,
    );
  });

  it("shows error state with retry on fetch failure", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("Calculate fail"));
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText("Calculate fail")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /retry loading savings estimate/i }),
    ).toBeInTheDocument();
  });

  it("clamps negative savings to $0 display", async () => {
    mockFetchAnalytics.mockResolvedValue({
      ..._savings,
      estimated_annual_savings_vs_best: -50,
      estimated_monthly_savings_vs_best: -5,
    });
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("annual-savings-amount")).toHaveTextContent(
        "$0",
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// ConnectionHealthCard
// ---------------------------------------------------------------------------

describe("ConnectionHealthCard", () => {
  beforeEach(() => mockFetchAnalytics.mockReset());

  it("shows loading state on mount", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<ConnectionHealthCard refreshKey={0} />);
    expect(screen.getByTestId("connection-health-loading")).toBeInTheDocument();
  });

  it("shows all-healthy message when no issues", async () => {
    mockFetchAnalytics.mockResolvedValue({
      stale_connections: [],
      rate_change_alerts: [],
    });
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(
        screen.getByText(/all connections are healthy/i),
      ).toBeInTheDocument(),
    );
  });

  it("renders stale connection with testid", async () => {
    mockFetchAnalytics.mockResolvedValue(_health);
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("stale-connection-conn-1")).toBeInTheDocument(),
    );
    expect(screen.getByText("GreenPower")).toBeInTheDocument();
    expect(screen.getByText(/41 day/)).toBeInTheDocument();
  });

  it("renders rate change alert with testid", async () => {
    mockFetchAnalytics.mockResolvedValue(_health);
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("rate-alert-alert-1")).toBeInTheDocument(),
    );
    expect(screen.getByText(/BlueSky rate increased/)).toBeInTheDocument();
  });

  it("shows issue count badge when there are issues", async () => {
    mockFetchAnalytics.mockResolvedValue(_health);
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText("2 issues")).toBeInTheDocument(),
    );
  });

  it("shows singular 'issue' when exactly 1", async () => {
    mockFetchAnalytics.mockResolvedValue({
      stale_connections: [_health.stale_connections[0]!],
      rate_change_alerts: [],
    });
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText("1 issue")).toBeInTheDocument(),
    );
  });

  it("shows sync button when onSync is provided", async () => {
    mockFetchAnalytics.mockResolvedValue(_health);
    const onSync = jest.fn().mockResolvedValue(undefined);
    render(<ConnectionHealthCard refreshKey={0} onSync={onSync} />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /sync greenpower/i }),
      ).toBeInTheDocument(),
    );
  });

  it("omits sync button when onSync is not provided", async () => {
    mockFetchAnalytics.mockResolvedValue(_health);
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("stale-connection-conn-1")).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("button", { name: /sync/i }),
    ).not.toBeInTheDocument();
  });

  it("shows error state with retry button", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("Health check failed"));
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText("Health check failed")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /retry loading connection health/i }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// RateHistoryCard
// ---------------------------------------------------------------------------

describe("RateHistoryCard", () => {
  beforeEach(() => mockFetchAnalytics.mockReset());

  it("shows loading state on mount", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<RateHistoryCard refreshKey={0} />);
    expect(screen.getByTestId("rate-history-loading")).toBeInTheDocument();
  });

  it("shows no history message when data_points is empty", async () => {
    mockFetchAnalytics.mockResolvedValue({ data_points: [] });
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(
        screen.getByText(/no rate history available/i),
      ).toBeInTheDocument(),
    );
  });

  it("renders rate history table with data", async () => {
    mockFetchAnalytics.mockResolvedValue(_history);
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("rate-history-table")).toBeInTheDocument(),
    );
    expect(screen.getAllByText("GreenPower").length).toBeGreaterThan(0);
    // user_rate * 100 = 14.00 c/kWh
    expect(screen.getByText("14.00 c/kWh")).toBeInTheDocument();
  });

  it("does not show Show all button when <= 12 data points", async () => {
    mockFetchAnalytics.mockResolvedValue(_history);
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("rate-history-table")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("show-more-history")).not.toBeInTheDocument();
  });

  it("shows Show all button when > 12 data points", async () => {
    const manyPoints = Array.from({ length: 15 }, (_, i) => ({
      date: `2026-05-${String(i + 1).padStart(2, "0")}`,
      rate: 0.13 + i * 0.001,
      supplier: "GreenPower",
    }));
    mockFetchAnalytics.mockResolvedValue({ data_points: manyPoints });
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("show-more-history")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("show-more-history")).toHaveTextContent(
      "Show all 15 entries",
    );
  });

  it("expands to show all entries when Show all is clicked", async () => {
    const manyPoints = Array.from({ length: 15 }, (_, i) => ({
      date: `2026-05-${String(i + 1).padStart(2, "0")}`,
      rate: 0.13,
      supplier: "GreenPower",
    }));
    mockFetchAnalytics.mockResolvedValue({ data_points: manyPoints });
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("show-more-history")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("show-more-history"));
    expect(screen.getByTestId("show-more-history")).toHaveTextContent(
      "Show less",
    );
  });

  it("shows error state with retry button", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("History unavailable"));
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText("History unavailable")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /retry loading rate history/i }),
    ).toBeInTheDocument();
  });
});
