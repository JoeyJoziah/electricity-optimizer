import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetPropanePrices = jest.fn();
const mockGetPropaneHistory = jest.fn();
const mockGetPropaneComparison = jest.fn();
const mockGetPropaneTiming = jest.fn();

jest.mock("@/lib/api/propane", () => ({
  getPropanePrices: (...args: unknown[]) => mockGetPropanePrices(...args),
  getPropaneHistory: (...args: unknown[]) => mockGetPropaneHistory(...args),
  getPropaneComparison: (...args: unknown[]) =>
    mockGetPropaneComparison(...args),
  getPropaneTiming: (...args: unknown[]) => mockGetPropaneTiming(...args),
}));

import {
  usePropanePrices,
  usePropaneHistory,
  usePropaneComparison,
  usePropaneTiming,
} from "@/lib/hooks/usePropane";

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

describe("usePropanePrices", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockGetPropanePrices.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => usePropanePrices(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("usePropaneHistory", () => {
  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => usePropaneHistory(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetPropaneHistory.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => usePropaneHistory("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("usePropaneComparison", () => {
  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => usePropaneComparison(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetPropaneComparison.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => usePropaneComparison("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("usePropaneTiming", () => {
  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => usePropaneTiming(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetPropaneTiming.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => usePropaneTiming("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
