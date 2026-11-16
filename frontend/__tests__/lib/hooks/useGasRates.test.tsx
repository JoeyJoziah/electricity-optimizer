import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  useGasRates,
  useGasHistory,
  useGasStats,
  useDeregulatedGasStates,
  useGasSupplierComparison,
} from "@/lib/hooks/useGasRates";
import "@testing-library/jest-dom";
import React from "react";

const mockGetGasRates = jest.fn();
const mockGetGasHistory = jest.fn();
const mockGetGasStats = jest.fn();
const mockGetDeregulatedGasStates = jest.fn();
const mockCompareGasSuppliers = jest.fn();

jest.mock("@/lib/api/gas-rates", () => ({
  getGasRates: (...args: unknown[]) => mockGetGasRates(...args),
  getGasHistory: (...args: unknown[]) => mockGetGasHistory(...args),
  getGasStats: (...args: unknown[]) => mockGetGasStats(...args),
  getDeregulatedGasStates: (...args: unknown[]) =>
    mockGetDeregulatedGasStates(...args),
  compareGasSuppliers: (...args: unknown[]) => mockCompareGasSuppliers(...args),
}));

const mockRatesData = {
  region: "us_ct",
  utility_type: "natural_gas",
  unit: "$/therm",
  is_deregulated: true,
  count: 1,
  prices: [
    {
      id: "1",
      supplier: "EIA Average",
      price: "1.2500",
      unit: "$/therm",
      timestamp: "2026-03-10T00:00:00Z",
      source: "eia",
    },
  ],
};

const mockHistoryData = {
  region: "us_ct",
  utility_type: "natural_gas",
  period_days: 30,
  count: 2,
  prices: [
    {
      price: "1.2500",
      timestamp: "2026-03-10T00:00:00Z",
      supplier: "EIA Average",
    },
    {
      price: "1.2000",
      timestamp: "2026-03-03T00:00:00Z",
      supplier: "EIA Average",
    },
  ],
};

const mockStatsData = {
  region: "us_ct",
  utility_type: "natural_gas",
  unit: "$/therm",
  avg_price: "1.2250",
  min_price: "1.2000",
  max_price: "1.2500",
  count: 2,
};

const mockDeregulatedData = {
  count: 2,
  states: [
    {
      state_code: "CT",
      state_name: "Connecticut",
      puc_name: "PURA",
      puc_website: null,
      comparison_tool_url: null,
    },
    {
      state_code: "OH",
      state_name: "Ohio",
      puc_name: "PUCO",
      puc_website: null,
      comparison_tool_url: null,
    },
  ],
};

const mockCompareData = {
  region: "us_ct",
  is_deregulated: true,
  unit: "$/therm",
  suppliers: [
    {
      supplier: "Direct Energy",
      price: "1.1000",
      timestamp: "2026-03-10T00:00:00Z",
      source: "eia",
    },
    {
      supplier: "Constellation",
      price: "1.2500",
      timestamp: "2026-03-10T00:00:00Z",
      source: "eia",
    },
  ],
  cheapest: "Direct Energy",
};

describe("useGasRates hooks", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });

    mockGetGasRates.mockResolvedValue(mockRatesData);
    mockGetGasHistory.mockResolvedValue(mockHistoryData);
    mockGetGasStats.mockResolvedValue(mockStatsData);
    mockGetDeregulatedGasStates.mockResolvedValue(mockDeregulatedData);
    mockCompareGasSuppliers.mockResolvedValue(mockCompareData);
  });

  afterEach(() => {
    queryClient.clear();
    jest.clearAllMocks();
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("useGasRates returns gas rate data", async () => {
    const { result } = renderHook(() => useGasRates("us_ct"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockRatesData);
    expect(result.current.data?.prices[0]!.price).toBe("1.2500");
    expect(mockGetGasRates).toHaveBeenCalledWith(
      { region: "us_ct", limit: undefined },
      expect.anything(),
    );
  });

  it("useGasRates(null) is disabled", () => {
    const { result } = renderHook(() => useGasRates(null), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGetGasRates).not.toHaveBeenCalled();
  });

  it("useGasHistory returns history data", async () => {
    const { result } = renderHook(() => useGasHistory("us_ct", 30), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.prices).toHaveLength(2);
    expect(mockGetGasHistory).toHaveBeenCalledWith(
      { region: "us_ct", days: 30 },
      expect.anything(),
    );
  });

  it("useGasHistory(null) is disabled", () => {
    const { result } = renderHook(() => useGasHistory(null), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGetGasHistory).not.toHaveBeenCalled();
  });

  it("useGasStats returns statistics", async () => {
    const { result } = renderHook(() => useGasStats("us_ct", 7), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.avg_price).toBe("1.2250");
    expect(mockGetGasStats).toHaveBeenCalledWith(
      { region: "us_ct", days: 7 },
      expect.anything(),
    );
  });

  it("useDeregulatedGasStates returns states list", async () => {
    const { result } = renderHook(() => useDeregulatedGasStates(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.count).toBe(2);
    expect(result.current.data?.states[0]!.state_code).toBe("CT");
  });

  it("useGasSupplierComparison returns suppliers", async () => {
    const { result } = renderHook(() => useGasSupplierComparison("us_ct"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.cheapest).toBe("Direct Energy");
    expect(result.current.data?.suppliers).toHaveLength(2);
    expect(mockCompareGasSuppliers).toHaveBeenCalledWith(
      "us_ct",
      expect.anything(),
    );
  });

  it("useGasSupplierComparison(null) is disabled", () => {
    const { result } = renderHook(() => useGasSupplierComparison(null), {
      wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockCompareGasSuppliers).not.toHaveBeenCalled();
  });

  it("hooks use correct query keys", async () => {
    renderHook(() => useGasRates("us_ct"), { wrapper });
    renderHook(() => useGasHistory("us_ct", 30), { wrapper });
    renderHook(() => useGasStats("us_ct", 7), { wrapper });
    renderHook(() => useDeregulatedGasStates(), { wrapper });
    renderHook(() => useGasSupplierComparison("us_ct"), { wrapper });

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll();
      const keys = queries.map((q) => q.queryKey);

      expect(keys).toContainEqual(["gas-rates", "us_ct", undefined]);
      expect(keys).toContainEqual(["gas-rates", "history", "us_ct", 30]);
      expect(keys).toContainEqual(["gas-rates", "stats", "us_ct", 7]);
      expect(keys).toContainEqual(["gas-rates", "deregulated-states"]);
      expect(keys).toContainEqual(["gas-rates", "compare", "us_ct"]);
    });
  });

  it("handles API errors", async () => {
    mockGetGasRates.mockRejectedValue(new Error("Gas API error"));

    const { result } = renderHook(() => useGasRates("us_ct"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error?.message).toBe("Gas API error");
  });
});
