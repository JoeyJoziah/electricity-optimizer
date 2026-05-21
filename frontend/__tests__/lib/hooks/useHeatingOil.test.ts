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
