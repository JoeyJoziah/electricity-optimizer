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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
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
