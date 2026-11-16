import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetHeatingOilPrices = jest.fn();
const mockGetHeatingOilHistory = jest.fn();
const mockGetHeatingOilDealers = jest.fn();
const mockGetHeatingOilComparison = jest.fn();

jest.mock("@/lib/api/heating-oil", () => ({
  getHeatingOilPrices: (...args: unknown[]) => mockGetHeatingOilPrices(...args),
  getHeatingOilHistory: (...args: unknown[]) =>
    mockGetHeatingOilHistory(...args),
  getHeatingOilDealers: (...args: unknown[]) =>
    mockGetHeatingOilDealers(...args),
  getHeatingOilComparison: (...args: unknown[]) =>
    mockGetHeatingOilComparison(...args),
}));

import {
  useHeatingOilPrices,
  useHeatingOilHistory,
  useHeatingOilDealers,
  useHeatingOilComparison,
} from "@/lib/hooks/useHeatingOil";
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

describe("useHeatingOilPrices", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockGetHeatingOilPrices.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useHeatingOilPrices(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useHeatingOilHistory", () => {
  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => useHeatingOilHistory(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetHeatingOilHistory.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useHeatingOilHistory("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useHeatingOilDealers", () => {
  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => useHeatingOilDealers(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetHeatingOilDealers.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useHeatingOilDealers("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useHeatingOilComparison", () => {
  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => useHeatingOilComparison(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetHeatingOilComparison.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useHeatingOilComparison("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/hooks/useHeatingOil.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  const mockGetPrices = mockGetHeatingOilPrices;
  const mockGetHistory = mockGetHeatingOilHistory;
  const mockGetDealers = mockGetHeatingOilDealers;
  const mockGetComparison = mockGetHeatingOilComparison;

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

  describe("useHeatingOilPrices", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetPrices.mockResolvedValue({
        prices: [{ state: "CT", price_per_gallon: 3.25 }],
        tracked_states: ["CT"],
      });
    });

    it("fetches prices", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useHeatingOilPrices("CT"), {
        wrapper,
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.prices).toHaveLength(1);
    });

    it("uses correct query key", async () => {
      const { wrapper, queryClient } = createWrapper();
      renderHook(() => useHeatingOilPrices("MA"), { wrapper });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual(["heating-oil", "prices", "MA"]);
      });
    });

    it("handles error", async () => {
      mockGetPrices.mockRejectedValue(new Error("API error"));
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useHeatingOilPrices("CT"), {
        wrapper,
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
    });
  });

  describe("useHeatingOilHistory", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetHistory.mockResolvedValue({ state: "CT", weeks: 12, history: [] });
    });

    it("fetches when state is provided", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useHeatingOilHistory("CT", 12), {
        wrapper,
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });

    it("uses correct query key with weeks", async () => {
      const { wrapper, queryClient } = createWrapper();
      renderHook(() => useHeatingOilHistory("NY", 8), { wrapper });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual(["heating-oil", "history", "NY", 8]);
      });
    });
  });

  describe("useHeatingOilDealers", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetDealers.mockResolvedValue([{ name: "Discount Oil", state: "CT" }]);
    });

    it("fetches dealers when state provided", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useHeatingOilDealers("CT"), {
        wrapper,
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe("useHeatingOilComparison", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetComparison.mockResolvedValue({
        state: "CT",
        price_per_gallon: 3.25,
        national_avg: 3.1,
      });
    });

    it("fetches comparison when state provided", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useHeatingOilComparison("CT"), {
        wrapper,
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.national_avg).toBe(3.1);
    });
  });
}
