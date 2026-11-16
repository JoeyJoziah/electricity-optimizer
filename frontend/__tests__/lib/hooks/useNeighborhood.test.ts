import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetNeighborhoodComparison = jest.fn();

jest.mock("@/lib/api/neighborhood", () => ({
  getNeighborhoodComparison: (...args: unknown[]) =>
    mockGetNeighborhoodComparison(...args),
}));

import { useNeighborhoodComparison } from "@/lib/hooks/useNeighborhood";
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

describe("useNeighborhoodComparison", () => {
  it("is disabled when region is undefined", () => {
    const { result } = renderHook(
      () => useNeighborhoodComparison(undefined, "electricity"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when utilityType is undefined", () => {
    const { result } = renderHook(
      () => useNeighborhoodComparison("us_ct", undefined),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when both region and utilityType are provided", () => {
    mockGetNeighborhoodComparison.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () => useNeighborhoodComparison("us_ct", "electricity"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/hooks/useNeighborhood.test.ts (block-scoped so its helpers do not
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

  const mockResponse = {
    region: "us_ct",
    utility_type: "electricity",
    user_count: 42,
    percentile: 75,
    user_rate: 0.18,
    cheapest_supplier: "CheapElec",
    cheapest_rate: 0.12,
    avg_rate: 0.16,
    potential_savings: 7.5,
  };

  describe("useNeighborhoodComparison", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetNeighborhoodComparison.mockResolvedValue(mockResponse);
    });

    it("fetches comparison when both params provided", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(
        () => useNeighborhoodComparison("us_ct", "electricity"),
        { wrapper },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.user_count).toBe(42);
      expect(result.current.data?.potential_savings).toBe(7.5);
    });

    it("uses correct query key", async () => {
      const { wrapper, queryClient } = createWrapper();
      renderHook(() => useNeighborhoodComparison("us_ny", "natural_gas"), {
        wrapper,
      });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual([
          "neighborhood",
          "compare",
          "us_ny",
          "natural_gas",
        ]);
      });
    });

    it("handles error", async () => {
      mockGetNeighborhoodComparison.mockRejectedValue(
        new Error("Not enough data"),
      );
      const { wrapper } = createWrapper();
      const { result } = renderHook(
        () => useNeighborhoodComparison("us_ct", "electricity"),
        { wrapper },
      );

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error?.message).toBe("Not enough data");
    });

    it("passes AbortSignal", async () => {
      const { wrapper } = createWrapper();
      renderHook(() => useNeighborhoodComparison("us_ct", "electricity"), {
        wrapper,
      });

      await waitFor(() =>
        expect(mockGetNeighborhoodComparison).toHaveBeenCalled(),
      );
      expect(mockGetNeighborhoodComparison).toHaveBeenCalledWith(
        "us_ct",
        "electricity",
        expect.any(AbortSignal),
      );
    });
  });
}
