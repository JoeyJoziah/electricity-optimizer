import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetOptimizationReport = jest.fn();

jest.mock("@/lib/api/reports", () => ({
  getOptimizationReport: (...args: unknown[]) =>
    mockGetOptimizationReport(...args),
}));

import { useOptimizationReport } from "@/lib/hooks/useReports";

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

describe("useOptimizationReport", () => {
  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => useOptimizationReport(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetOptimizationReport.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useOptimizationReport("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
