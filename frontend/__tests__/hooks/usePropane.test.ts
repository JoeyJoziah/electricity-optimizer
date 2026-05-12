import { renderHook, waitFor } from "@testing-library/react";
import React, { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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

const fakePrices = [{ state: "CT", price_per_gallon: 3.2 }];
const fakeHistory = [{ week: "2026-05-01", price: 3.1 }];
const fakeComparison = { propane: 3.2, electricity_equivalent: 4.1 };
const fakeTiming = { recommendation: "buy_now", confidence: 0.8 };

describe("usePropanePrices", () => {
  beforeEach(() => jest.clearAllMocks());

  it("fires the query even when state is undefined (always enabled)", async () => {
    mockGetPropanePrices.mockResolvedValue(fakePrices);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePropanePrices(undefined), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPropanePrices).toHaveBeenCalledWith(
      undefined,
      expect.any(AbortSignal),
    );
  });

  it("fires the query with state when provided", async () => {
    mockGetPropanePrices.mockResolvedValue(fakePrices);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePropanePrices("CT"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPropanePrices).toHaveBeenCalledWith(
      "CT",
      expect.any(AbortSignal),
    );
    expect(result.current.data).toEqual(fakePrices);
  });

  it("query key includes state", async () => {
    mockGetPropanePrices.mockResolvedValue(fakePrices);
    const { queryClient, wrapper } = createWrapper();
    renderHook(() => usePropanePrices("NY"), { wrapper });
    await waitFor(() =>
      expect(
        queryClient.getQueryData(["propane", "prices", "NY"]),
      ).toBeDefined(),
    );
  });
});

describe("usePropaneHistory", () => {
  beforeEach(() => jest.clearAllMocks());

  it("is disabled when state is undefined", () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePropaneHistory(undefined), {
      wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGetPropaneHistory).not.toHaveBeenCalled();
  });

  it("fires the query when state is provided", async () => {
    mockGetPropaneHistory.mockResolvedValue(fakeHistory);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePropaneHistory("CT", 12), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPropaneHistory).toHaveBeenCalledWith(
      "CT",
      12,
      expect.any(AbortSignal),
    );
    expect(result.current.data).toEqual(fakeHistory);
  });

  it("query key includes state and weeks", async () => {
    mockGetPropaneHistory.mockResolvedValue(fakeHistory);
    const { queryClient, wrapper } = createWrapper();
    renderHook(() => usePropaneHistory("MA", 8), { wrapper });
    await waitFor(() =>
      expect(
        queryClient.getQueryData(["propane", "history", "MA", 8]),
      ).toBeDefined(),
    );
  });
});

describe("usePropaneComparison", () => {
  beforeEach(() => jest.clearAllMocks());

  it("is disabled when state is undefined", () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePropaneComparison(undefined), {
      wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGetPropaneComparison).not.toHaveBeenCalled();
  });

  it("fires the query when state is provided", async () => {
    mockGetPropaneComparison.mockResolvedValue(fakeComparison);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePropaneComparison("CT"), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(fakeComparison);
  });
});

describe("usePropaneTiming", () => {
  beforeEach(() => jest.clearAllMocks());

  it("is disabled when state is undefined", () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePropaneTiming(undefined), {
      wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGetPropaneTiming).not.toHaveBeenCalled();
  });

  it("fires the query when state is provided", async () => {
    mockGetPropaneTiming.mockResolvedValue(fakeTiming);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePropaneTiming("CT"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(fakeTiming);
  });

  it("query key includes state", async () => {
    mockGetPropaneTiming.mockResolvedValue(fakeTiming);
    const { queryClient, wrapper } = createWrapper();
    renderHook(() => usePropaneTiming("NH"), { wrapper });
    await waitFor(() =>
      expect(
        queryClient.getQueryData(["propane", "timing", "NH"]),
      ).toBeDefined(),
    );
  });
});
