import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetCurrentPrices = jest.fn();
const mockGetPriceHistory = jest.fn();
const mockGetPriceForecast = jest.fn();
const mockGetOptimalPeriods = jest.fn();

jest.mock("@/lib/api/prices", () => ({
  getCurrentPrices: (...args: unknown[]) => mockGetCurrentPrices(...args),
  getPriceHistory: (...args: unknown[]) => mockGetPriceHistory(...args),
  getPriceForecast: (...args: unknown[]) => mockGetPriceForecast(...args),
  getOptimalPeriods: (...args: unknown[]) => mockGetOptimalPeriods(...args),
}));

import {
  useCurrentPrices,
  usePriceHistory,
  usePriceForecast,
  useOptimalPeriods,
  useRefreshPrices,
} from "@/lib/hooks/usePrices";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useCurrentPrices", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => useCurrentPrices(null), {
      wrapper: makeWrapper(),
    });
    // fetchStatus idle means the query was not triggered
    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.isLoading).toBe(false);
  });

  it("is disabled when region is undefined", () => {
    const { result } = renderHook(() => useCurrentPrices(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when region is a non-empty string", () => {
    mockGetCurrentPrices.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCurrentPrices("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("usePriceHistory", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => usePriceHistory(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when enabled=false", () => {
    const { result } = renderHook(() => usePriceHistory("us_ct", 24, false), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("converts hours to days (ceil) for API call", () => {
    mockGetPriceHistory.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => usePriceHistory("us_ct", 36), {
      wrapper: makeWrapper(),
    });
    // 36 hours → ceil(36/24) = 2 days → queryKey includes 2
    expect(result.current.fetchStatus).toBe("fetching");
    expect(mockGetPriceHistory).toHaveBeenCalledWith(
      expect.objectContaining({ days: 2 }),
      expect.anything(),
    );
  });
});

describe("usePriceForecast", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => usePriceForecast(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when enabled=false", () => {
    const { result } = renderHook(() => usePriceForecast("us_ct", 24, false), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useOptimalPeriods", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => useOptimalPeriods(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when region is provided", () => {
    mockGetOptimalPeriods.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useOptimalPeriods("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useRefreshPrices", () => {
  it("returns a function", () => {
    const { result } = renderHook(() => useRefreshPrices(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current).toBe("function");
  });

  it("is stable across re-renders (same reference)", () => {
    let renderCount = 0;
    const { result, rerender } = renderHook(
      () => {
        renderCount++;
        return useRefreshPrices();
      },
      { wrapper: makeWrapper() },
    );

    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });
});
