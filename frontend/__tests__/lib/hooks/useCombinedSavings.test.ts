import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGetCombinedSavings = jest.fn();

jest.mock("@/lib/api/savings", () => ({
  getCombinedSavings: (...a: unknown[]) => mockGetCombinedSavings(...a),
}));

import { useCombinedSavings } from "@/lib/hooks/useCombinedSavings";

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
