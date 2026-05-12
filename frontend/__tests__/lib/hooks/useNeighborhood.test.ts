import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetNeighborhoodComparison = jest.fn();

jest.mock("@/lib/api/neighborhood", () => ({
  getNeighborhoodComparison: (...args: unknown[]) =>
    mockGetNeighborhoodComparison(...args),
}));

import { useNeighborhoodComparison } from "@/lib/hooks/useNeighborhood";

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

describe("useNeighborhoodComparison", () => {
  it("is disabled when region is undefined", () => {
    const { result } = renderHook(
      () => useNeighborhoodComparison(undefined, "electricity"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when utilityType is undefined", () => {
    const { result } = renderHook(
      () => useNeighborhoodComparison("us_ct", undefined),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when both region and utilityType are provided", () => {
    mockGetNeighborhoodComparison.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () => useNeighborhoodComparison("us_ct", "electricity"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
