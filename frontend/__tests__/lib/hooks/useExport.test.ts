import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockExportRates = jest.fn();
const mockGetExportTypes = jest.fn();

jest.mock("@/lib/api/export", () => ({
  exportRates: (...args: unknown[]) => mockExportRates(...args),
  getExportTypes: (...args: unknown[]) => mockGetExportTypes(...args),
}));

import { useExportRates, useExportTypes } from "@/lib/hooks/useExport";

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

describe("useExportRates", () => {
  it("is disabled by default (enabled=false)", () => {
    const { result } = renderHook(
      () => useExportRates("electricity", "json", "CT"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when utilityType is not provided even with enabled=true", () => {
    const { result } = renderHook(
      () => useExportRates(undefined, "json", "CT", true),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when enabled=true and utilityType is provided", () => {
    mockExportRates.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () => useExportRates("electricity", "json", "CT", true),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useExportTypes", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockGetExportTypes.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useExportTypes(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
