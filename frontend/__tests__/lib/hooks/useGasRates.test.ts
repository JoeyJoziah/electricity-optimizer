import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

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

import {
  useGasRates,
  useGasHistory,
  useGasStats,
  useDeregulatedGasStates,
  useGasSupplierComparison,
} from "@/lib/hooks/useGasRates";

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

describe("useGasRates", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => useGasRates(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when region is provided", () => {
    mockGetGasRates.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useGasRates("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useGasHistory", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => useGasHistory(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when region is provided", () => {
    mockGetGasHistory.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useGasHistory("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useGasStats", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => useGasStats(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when region is provided", () => {
    mockGetGasStats.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useGasStats("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useDeregulatedGasStates", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockGetDeregulatedGasStates.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDeregulatedGasStates(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useGasSupplierComparison", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => useGasSupplierComparison(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when region is provided", () => {
    mockCompareGasSuppliers.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useGasSupplierComparison("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
