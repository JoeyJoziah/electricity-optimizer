import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGetCombinedSavings = jest.fn();

jest.mock("@/lib/api/savings", () => ({
  getCombinedSavings: (...a: unknown[]) => mockGetCombinedSavings(...a),
}));

import { useCombinedSavings } from "@/lib/hooks/useCombinedSavings";
import { ReactNode } from "react";
import "@testing-library/jest-dom";

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestWrapper";
  return Wrapper;
}

beforeEach(() => {
  mockGetCombinedSavings.mockReset();
});

describe("useCombinedSavings", () => {
  it("returns data on successful fetch", async () => {
    const mockData = {
      electricity: 150,
      gas: 80,
      total: 230,
      currency: "USD",
    };
    mockGetCombinedSavings.mockResolvedValueOnce(mockData);

    const { result } = renderHook(() => useCombinedSavings(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockData);
  });

  it("sets error state on fetch failure", async () => {
    mockGetCombinedSavings.mockRejectedValueOnce(new Error("Network error"));

    const { result } = renderHook(() => useCombinedSavings(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it("starts in loading state", () => {
    mockGetCombinedSavings.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(() => useCombinedSavings(), {
      wrapper: makeWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });

  it("passes signal to getCombinedSavings", async () => {
    mockGetCombinedSavings.mockResolvedValueOnce({ total: 0 });

    renderHook(() => useCombinedSavings(), { wrapper: makeWrapper() });

    await waitFor(() => expect(mockGetCombinedSavings).toHaveBeenCalled());
    const callArg = mockGetCombinedSavings.mock.calls[0][0];
    expect(callArg === undefined || callArg instanceof AbortSignal).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/hooks/useCombinedSavings.test.ts (block-scoped so its helpers do not
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
    total_monthly_savings: 42.5,
    breakdown: [
      { utility_type: "electricity", monthly_savings: 30 },
      { utility_type: "natural_gas", monthly_savings: 12.5 },
    ],
    savings_rank_pct: 85,
  };

  describe("useCombinedSavings", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetCombinedSavings.mockResolvedValue(mockResponse);
    });

    it("fetches combined savings", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useCombinedSavings(), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total_monthly_savings).toBe(42.5);
      expect(result.current.data?.breakdown).toHaveLength(2);
    });

    it("uses correct query key", async () => {
      const { wrapper, queryClient } = createWrapper();
      renderHook(() => useCombinedSavings(), { wrapper });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual(["savings", "combined"]);
      });
    });

    it("handles error", async () => {
      mockGetCombinedSavings.mockRejectedValue(
        new Error("Service unavailable"),
      );
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useCombinedSavings(), { wrapper });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error?.message).toBe("Service unavailable");
    });

    it("passes AbortSignal to API function", async () => {
      const { wrapper } = createWrapper();
      renderHook(() => useCombinedSavings(), { wrapper });

      await waitFor(() => expect(mockGetCombinedSavings).toHaveBeenCalled());
      expect(mockGetCombinedSavings).toHaveBeenCalledWith(
        expect.any(AbortSignal),
      );
    });
  });
}
