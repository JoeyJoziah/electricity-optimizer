import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockFetchEventSource = jest.fn();

jest.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: (...args: unknown[]) => mockFetchEventSource(...args),
}));

jest.mock("@/lib/config/env", () => ({
  API_URL: "https://api.test.invalid",
}));

import {
  useRealtimePrices,
  useRealtimeOptimization,
  useRealtimeSubscription,
} from "@/lib/hooks/useRealtime";

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

describe("useRealtimePrices", () => {
  beforeEach(() => mockFetchEventSource.mockReset());

  it("does not call fetchEventSource when region is null", () => {
    mockFetchEventSource.mockReturnValue(new Promise(() => {}));
    renderHook(() => useRealtimePrices(null), { wrapper: makeWrapper() });
    expect(mockFetchEventSource).not.toHaveBeenCalled();
  });

  it("does not call fetchEventSource when region is undefined", () => {
    renderHook(() => useRealtimePrices(undefined), { wrapper: makeWrapper() });
    expect(mockFetchEventSource).not.toHaveBeenCalled();
  });

  it("calls fetchEventSource with region URL when region is provided", () => {
    mockFetchEventSource.mockReturnValue(new Promise(() => {}));
    renderHook(() => useRealtimePrices("us_ct"), { wrapper: makeWrapper() });
    expect(mockFetchEventSource).toHaveBeenCalledWith(
      expect.stringContaining("us_ct"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("starts with isConnected=false and lastPrice=null", () => {
    mockFetchEventSource.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useRealtimePrices("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isConnected).toBe(false);
    expect(result.current.lastPrice).toBeNull();
  });

  it("exposes disconnect function", () => {
    mockFetchEventSource.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useRealtimePrices("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.disconnect).toBe("function");
  });

  it("disconnect sets isConnected to false", () => {
    mockFetchEventSource.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useRealtimePrices("us_ct"), {
      wrapper: makeWrapper(),
    });
    act(() => {
      result.current.disconnect();
    });
    expect(result.current.isConnected).toBe(false);
  });
});

describe("useRealtimeOptimization", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("starts with isConnected=true after mount", () => {
    const { result } = renderHook(() => useRealtimeOptimization(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isConnected).toBe(true);
  });

  it("clears the interval on unmount without throwing", () => {
    const { unmount } = renderHook(() => useRealtimeOptimization(), {
      wrapper: makeWrapper(),
    });
    expect(() => unmount()).not.toThrow();
  });
});

describe("useRealtimeSubscription", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("starts with isConnected=true and lastUpdate=null", () => {
    const { result } = renderHook(
      () => useRealtimeSubscription({ table: "prices" }),
      { wrapper: makeWrapper() },
    );
    expect(result.current.isConnected).toBe(true);
    expect(result.current.lastUpdate).toBeNull();
  });

  it("sets lastUpdate after poll interval fires", () => {
    const onUpdate = jest.fn();
    const { result } = renderHook(
      () => useRealtimeSubscription({ table: "prices" }, onUpdate),
      { wrapper: makeWrapper() },
    );
    act(() => {
      jest.advanceTimersByTime(30_001);
    });
    expect(result.current.lastUpdate).toBeInstanceOf(Date);
    expect(onUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ table: "prices" }),
    );
  });

  it("clears the interval on unmount without throwing", () => {
    const { unmount } = renderHook(
      () => useRealtimeSubscription({ table: "prices" }),
      { wrapper: makeWrapper() },
    );
    expect(() => unmount()).not.toThrow();
  });
});
