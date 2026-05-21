import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockDiscoverUtilities = jest.fn();
const mockGetUtilityCompletion = jest.fn();

jest.mock("@/lib/api/utility-discovery", () => ({
  discoverUtilities: (...args: unknown[]) => mockDiscoverUtilities(...args),
  getUtilityCompletion: (...args: unknown[]) =>
    mockGetUtilityCompletion(...args),
}));

import {
  useUtilityDiscovery,
  useUtilityCompletion,
} from "@/lib/hooks/useUtilityDiscovery";

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

describe("useUtilityDiscovery", () => {
  it("is disabled when state is null", () => {
    const { result } = renderHook(() => useUtilityDiscovery(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when state is undefined", () => {
    const { result } = renderHook(() => useUtilityDiscovery(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockDiscoverUtilities.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useUtilityDiscovery("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useUtilityCompletion", () => {
  it("is disabled when state is null", () => {
    const { result } = renderHook(
      () => useUtilityCompletion(null, ["electricity"]),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when trackedTypes is empty", () => {
    const { result } = renderHook(() => useUtilityCompletion("CT", []), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state and trackedTypes are provided", () => {
    mockGetUtilityCompletion.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () => useUtilityCompletion("CT", ["electricity", "gas"]),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
