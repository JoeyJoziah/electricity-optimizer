import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetRateChanges = jest.fn();
const mockGetAlertPreferences = jest.fn();
const mockUpsertAlertPreference = jest.fn();

jest.mock("@/lib/api/rate-changes", () => ({
  getRateChanges: (...args: unknown[]) => mockGetRateChanges(...args),
  getAlertPreferences: (...args: unknown[]) => mockGetAlertPreferences(...args),
  upsertAlertPreference: (...args: unknown[]) =>
    mockUpsertAlertPreference(...args),
}));

import {
  useRateChanges,
  useAlertPreferences,
  useUpsertAlertPreference,
} from "@/lib/hooks/useRateChanges";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestWrapper";
  return Wrapper;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useRateChanges", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockGetRateChanges.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useRateChanges(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });

  it("passes params to API", () => {
    mockGetRateChanges.mockReturnValue(new Promise(() => {}));
    renderHook(
      () => useRateChanges({ utility_type: "electricity", region: "us_ct" }),
      { wrapper: makeWrapper() },
    );
    expect(mockGetRateChanges).toHaveBeenCalledWith(
      expect.objectContaining({ utility_type: "electricity", region: "us_ct" }),
      expect.anything(),
    );
  });
});

describe("useAlertPreferences", () => {
  it("fetches on mount", () => {
    mockGetAlertPreferences.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAlertPreferences(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useUpsertAlertPreference", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useUpsertAlertPreference(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });

  it("calls upsertAlertPreference on mutate", async () => {
    mockUpsertAlertPreference.mockResolvedValue(undefined);
    const { result } = renderHook(() => useUpsertAlertPreference(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate({
        utility_type: "electricity",
        threshold: 0.25,
      } as Parameters<typeof result.current.mutate>[0]);
    });
    expect(mockUpsertAlertPreference).toHaveBeenCalledTimes(1);
  });
});
