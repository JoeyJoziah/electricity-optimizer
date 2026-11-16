import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetWaterRates = jest.fn();
const mockGetWaterBenchmark = jest.fn();
const mockGetWaterTips = jest.fn();

jest.mock("@/lib/api/water", () => ({
  getWaterRates: (...args: unknown[]) => mockGetWaterRates(...args),
  getWaterBenchmark: (...args: unknown[]) => mockGetWaterBenchmark(...args),
  getWaterTips: (...args: unknown[]) => mockGetWaterTips(...args),
}));

import {
  useWaterRates,
  useWaterBenchmark,
  useWaterTips,
} from "@/lib/hooks/useWater";
import { waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import "@testing-library/jest-dom";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestWrapper";
  return Wrapper;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useWaterRates", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockGetWaterRates.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useWaterRates(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useWaterBenchmark", () => {
  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => useWaterBenchmark(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetWaterBenchmark.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useWaterBenchmark("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useWaterTips", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockGetWaterTips.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useWaterTips(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/hooks/useWater.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  function createWrapper() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    return {
      queryClient,
      wrapper: ({ children }: { children: ReactNode }) =>
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          children,
        ),
    };
  }

  describe("useWaterRates", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetWaterRates.mockResolvedValue({
        rates: [
          {
            id: "wr-1",
            municipality: "Hartford",
            state: "CT",
            rate_tiers: [],
            base_charge: 15,
          },
        ],
        count: 1,
      });
    });

    it("fetches water rates", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useWaterRates("CT"), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.rates).toHaveLength(1);
    });

    it("uses correct query key", async () => {
      const { wrapper, queryClient } = createWrapper();
      renderHook(() => useWaterRates("NY"), { wrapper });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual(["water", "rates", "NY"]);
      });
    });

    it("handles error", async () => {
      mockGetWaterRates.mockRejectedValue(new Error("Not available"));
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useWaterRates("CT"), { wrapper });

      await waitFor(() => expect(result.current.isError).toBe(true));
    });
  });

  describe("useWaterBenchmark", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetWaterBenchmark.mockResolvedValue({
        state: "CT",
        municipalities: 3,
        usage_gallons: 5760,
        avg_monthly_cost: 45,
        min_monthly_cost: 30,
        max_monthly_cost: 65,
        rates: [],
      });
    });

    it("fetches benchmark when state provided", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useWaterBenchmark("CT", 5000), {
        wrapper,
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.avg_monthly_cost).toBe(45);
    });

    it("uses correct query key with usage", async () => {
      const { wrapper, queryClient } = createWrapper();
      renderHook(() => useWaterBenchmark("CT", 8000), { wrapper });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual(["water", "benchmark", "CT", 8000]);
      });
    });
  });

  describe("useWaterTips", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetWaterTips.mockResolvedValue([
        { id: "tip-1", title: "Fix leaky faucets", savings_gallons: 3000 },
      ]);
    });

    it("fetches tips", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useWaterTips(), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(1);
    });

    it("uses correct query key", async () => {
      const { wrapper, queryClient } = createWrapper();
      renderHook(() => useWaterTips(), { wrapper });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual(["water", "tips"]);
      });
    });

    it("passes AbortSignal", async () => {
      const { wrapper } = createWrapper();
      renderHook(() => useWaterTips(), { wrapper });

      await waitFor(() => expect(mockGetWaterTips).toHaveBeenCalled());
      expect(mockGetWaterTips).toHaveBeenCalledWith(expect.any(AbortSignal));
    });
  });
}
