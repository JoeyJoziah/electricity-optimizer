import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import React from "react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockFetchAnalytics = jest.fn();

jest.mock("@/components/connections/analytics/types", () => ({
  ...jest.requireActual("@/components/connections/analytics/types"),
  fetchAnalytics: (...args: unknown[]) => mockFetchAnalytics(...args),
}));

import { RateComparisonCard } from "@/components/connections/analytics/RateComparisonCard";
import { SavingsEstimateCard } from "@/components/connections/analytics/SavingsEstimateCard";
import { RateHistoryCard } from "@/components/connections/analytics/RateHistoryCard";
import { ConnectionHealthCard } from "@/components/connections/analytics/ConnectionHealthCard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const rateComparison = {
  user_rate: 0.24,
  market_average: 0.2,
  delta: 0.04,
  percentage_difference: 20,
  is_above_average: true,
};

const savingsEstimate = {
  estimated_annual_savings_vs_best: 240,
  estimated_monthly_savings_vs_best: 20,
  current_annual_cost: 2400,
};

const rateHistory = {
  data_points: [
    { date: "2025-01-01", rate: 0.22, supplier: "EVERSOURCE" },
    { date: "2024-12-01", rate: 0.21, supplier: "EVERSOURCE" },
  ],
};

const connectionHealth = {
  stale_connections: [
    {
      id: "c1",
      supplier_name: "EVERSOURCE",
      last_sync_at: null,
      days_since_sync: 5,
    },
  ],
  rate_change_alerts: [
    {
      id: "a1",
      supplier_name: "UI",
      old_rate: 0.2,
      new_rate: 0.22,
      change_percentage: 10,
      detected_at: "2025-01-01",
    },
  ],
};

// ---------------------------------------------------------------------------
// RateComparisonCard
// ---------------------------------------------------------------------------

describe("RateComparisonCard", () => {
  beforeEach(() => mockFetchAnalytics.mockReset());

  it("shows loading state immediately", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<RateComparisonCard refreshKey={0} />);
    expect(screen.getByTestId("rate-comparison-loading")).toBeInTheDocument();
  });

  it("renders data on success", async () => {
    mockFetchAnalytics.mockResolvedValue(rateComparison);
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("rate-comparison-card")).toBeInTheDocument(),
    );
    expect(screen.getByText(/24.00/)).toBeInTheDocument();
    expect(screen.getByText(/20.00/)).toBeInTheDocument();
  });

  it("renders error state and retry button", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("fetch failed"));
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(
      screen.getByRole("button", { name: /retry loading rate comparison/i }),
    ).toBeInTheDocument();
  });

  it("retry button calls load again", async () => {
    mockFetchAnalytics
      .mockRejectedValueOnce(new Error("oops"))
      .mockReturnValue(new Promise(() => {}));
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    fireEvent.click(
      screen.getByRole("button", { name: /retry loading rate comparison/i }),
    );
    expect(mockFetchAnalytics).toHaveBeenCalledTimes(2);
  });

  it("shows above-market badge when is_above_average=true", async () => {
    mockFetchAnalytics.mockResolvedValue({
      ...rateComparison,
      is_above_average: true,
    });
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText(/above market average/i)).toBeInTheDocument(),
    );
  });

  it("shows below-market badge when is_above_average=false", async () => {
    mockFetchAnalytics.mockResolvedValue({
      ...rateComparison,
      is_above_average: false,
    });
    render(<RateComparisonCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText(/below market average/i)).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// SavingsEstimateCard
// ---------------------------------------------------------------------------

describe("SavingsEstimateCard", () => {
  beforeEach(() => mockFetchAnalytics.mockReset());

  it("shows loading state immediately", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<SavingsEstimateCard refreshKey={0} />);
    expect(screen.getByTestId("savings-estimate-loading")).toBeInTheDocument();
  });

  it("renders annual savings amount on success", async () => {
    mockFetchAnalytics.mockResolvedValue(savingsEstimate);
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("annual-savings-amount")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("annual-savings-amount")).toHaveTextContent(
      "$240",
    );
  });

  it("renders monthly savings as zero when savings are negative", async () => {
    mockFetchAnalytics.mockResolvedValue({
      ...savingsEstimate,
      estimated_annual_savings_vs_best: -50,
    });
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("annual-savings-amount")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("annual-savings-amount")).toHaveTextContent("$0");
  });

  it("shows error state and retry button", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("api error"));
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(
      screen.getByRole("button", { name: /retry loading savings estimate/i }),
    ).toBeInTheDocument();
  });

  it("renders monthly kWh input", async () => {
    mockFetchAnalytics.mockResolvedValue(savingsEstimate);
    render(<SavingsEstimateCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("savings-estimate-card")).toBeInTheDocument(),
    );
    const input = screen.getByLabelText(/monthly electricity usage/i);
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue(900);
  });
});

// ---------------------------------------------------------------------------
// RateHistoryCard
// ---------------------------------------------------------------------------

describe("RateHistoryCard", () => {
  beforeEach(() => mockFetchAnalytics.mockReset());

  it("shows loading state immediately", () => {
    mockFetchAnalytics.mockReturnValue(new Promise(() => {}));
    render(<RateHistoryCard refreshKey={0} />);
    expect(screen.getByTestId("rate-history-loading")).toBeInTheDocument();
  });

  it("renders history table rows on success", async () => {
    mockFetchAnalytics.mockResolvedValue(rateHistory);
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("rate-history-table")).toBeInTheDocument(),
    );
    expect(screen.getAllByText("EVERSOURCE")).toHaveLength(2);
  });

  it("shows empty state when no data points", async () => {
    mockFetchAnalytics.mockResolvedValue({ data_points: [] });
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(
        screen.getByText(/no rate history available/i),
      ).toBeInTheDocument(),
    );
  });

  it("shows 'Show all' button when > 12 entries", async () => {
    const points = Array.from({ length: 15 }, (_, i) => ({
      date: `2025-0${(i % 9) + 1}-01`,
      rate: 0.2 + i * 0.001,
      supplier: "EVERSOURCE",
    }));
    mockFetchAnalytics.mockResolvedValue({ data_points: points });
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("show-more-history")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("show-more-history")).toHaveTextContent(
      /show all 15/i,
    );
  });

  it("shows error state and retry button", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("history error"));
    render(<RateHistoryCard refreshKey={0} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(
      screen.getByRole("button", { name: /retry loading rate history/i }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ConnectionHealthCard
// ---------------------------------------------------------------------------

describe("ConnectionHealthCard", () => {
  beforeEach(() => mockFetchAnalytics.mockReset());

  it("shows loading state immediately", () => {
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

  it("renders stale connection entry", async () => {
    mockFetchAnalytics.mockResolvedValue(connectionHealth);
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("stale-connection-c1")).toBeInTheDocument(),
    );
    expect(screen.getByText("EVERSOURCE")).toBeInTheDocument();
    expect(screen.getByText(/5 days ago/i)).toBeInTheDocument();
  });

  it("renders rate change alert entry", async () => {
    mockFetchAnalytics.mockResolvedValue(connectionHealth);
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("rate-alert-a1")).toBeInTheDocument(),
    );
    expect(screen.getByText(/UI rate increased/i)).toBeInTheDocument();
  });

  it("shows issue badge count", async () => {
    mockFetchAnalytics.mockResolvedValue(connectionHealth);
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() =>
      expect(screen.getByText("2 issues")).toBeInTheDocument(),
    );
  });

  it("shows Sync Now button when onSync is provided", async () => {
    mockFetchAnalytics.mockResolvedValue(connectionHealth);
    const onSync = jest.fn().mockResolvedValue(undefined);
    render(<ConnectionHealthCard refreshKey={0} onSync={onSync} />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /sync eversource/i }),
      ).toBeInTheDocument(),
    );
  });

  it("shows error state and retry button", async () => {
    mockFetchAnalytics.mockRejectedValue(new Error("health error"));
    render(<ConnectionHealthCard refreshKey={0} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(
      screen.getByRole("button", { name: /retry loading connection health/i }),
    ).toBeInTheDocument();
  });
});
