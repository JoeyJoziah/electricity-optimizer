import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetCombinedSavings = jest.fn();
const mockApiClientGet = jest.fn();

jest.mock("@/lib/api/savings", () => ({
  getCombinedSavings: (...args: unknown[]) => mockGetCombinedSavings(...args),
}));

jest.mock("@/lib/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockApiClientGet(...args),
  },
}));

import { useCombinedSavings } from "@/lib/hooks/useCombinedSavings";
import { useSavingsSummary } from "@/lib/hooks/useSavings";

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

describe("useCombinedSavings", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockGetCombinedSavings.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCombinedSavings(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
    expect(mockGetCombinedSavings).toHaveBeenCalledTimes(1);
  });
});

describe("useSavingsSummary", () => {
  it("is enabled by default", () => {
    mockApiClientGet.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useSavingsSummary(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });

  it("is disabled when enabled=false", () => {
    const { result } = renderHook(() => useSavingsSummary(false), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});
