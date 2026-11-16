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
import { waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import "@testing-library/jest-dom";

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

// ---------------------------------------------------------------------------
// Cases merged from __tests__/hooks/useRateChanges.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  // --- Helpers ---

  function createWrapper() {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
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

  // --- Mock data ---

  const mockRateChangesResponse = {
    changes: [
      {
        id: "rc-1",
        utility_type: "electricity",
        region: "us_ct",
        supplier: "Eversource",
        previous_price: 0.24,
        current_price: 0.22,
        change_pct: -8.33,
        change_direction: "decrease",
        detected_at: "2026-03-15T08:00:00Z",
        recommendation_supplier: "NextEra",
        recommendation_price: 0.2,
        recommendation_savings: 0.02,
      },
    ],
    total: 1,
  };

  const mockPreferencesResponse = {
    preferences: [
      {
        id: "pref-1",
        user_id: "user-1",
        utility_type: "electricity",
        enabled: true,
        channels: ["email"],
        cadence: "immediate",
        created_at: "2026-03-01T10:00:00Z",
        updated_at: "2026-03-01T10:00:00Z",
      },
    ],
  };

  // ==========================================================================
  // useRateChanges
  // ==========================================================================
  describe("useRateChanges", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetRateChanges.mockResolvedValue(mockRateChangesResponse);
    });

    it("fetches rate changes without params", async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useRateChanges(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockRateChangesResponse);
      expect(mockGetRateChanges).toHaveBeenCalledWith(
        undefined,
        expect.anything(),
      );
    });

    it("fetches rate changes with params", async () => {
      const { wrapper } = createWrapper();

      const params = {
        utility_type: "electricity",
        region: "us_ct",
        days: 7,
        limit: 10,
      };
      const { result } = renderHook(() => useRateChanges(params), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockGetRateChanges).toHaveBeenCalledWith(
        params,
        expect.anything(),
      );
    });

    it("uses destructured primitive values in queryKey instead of object", async () => {
      const { wrapper, queryClient } = createWrapper();

      renderHook(
        () =>
          useRateChanges({
            utility_type: "electricity",
            region: "us_ct",
            days: 7,
            limit: 10,
          }),
        { wrapper },
      );

      await waitFor(() => {
        const queries = queryClient.getQueryCache().getAll();
        const keys = queries.map((q) => q.queryKey);
        // Should contain destructured primitives, NOT the params object
        expect(keys).toContainEqual([
          "rate-changes",
          "electricity",
          "us_ct",
          7,
          10,
        ]);
      });
    });

    it("uses undefined placeholders in queryKey for missing params", async () => {
      const { wrapper, queryClient } = createWrapper();

      renderHook(() => useRateChanges({ utility_type: "electricity" }), {
        wrapper,
      });

      await waitFor(() => {
        const queries = queryClient.getQueryCache().getAll();
        const keys = queries.map((q) => q.queryKey);
        expect(keys).toContainEqual([
          "rate-changes",
          "electricity",
          undefined,
          undefined,
          undefined,
        ]);
      });
    });

    it("does not refetch when a new params object with same values is passed", async () => {
      const { wrapper } = createWrapper();

      const params1 = { utility_type: "electricity", region: "us_ct" };
      const params2 = { utility_type: "electricity", region: "us_ct" }; // new ref, same values

      const { rerender } = renderHook(
        ({ params }: { params: typeof params1 }) => useRateChanges(params),
        {
          wrapper,
          initialProps: { params: params1 },
        },
      );

      await waitFor(() => {
        expect(mockGetRateChanges).toHaveBeenCalledTimes(1);
      });

      rerender({ params: params2 });

      // Should NOT trigger a second fetch because the destructured primitives are identical
      await waitFor(() => {
        expect(mockGetRateChanges).toHaveBeenCalledTimes(1);
      });
    });

    it("refetches when a param value changes", async () => {
      const { wrapper } = createWrapper();

      const { rerender } = renderHook(
        ({ region }: { region: string }) =>
          useRateChanges({ utility_type: "electricity", region }),
        {
          wrapper,
          initialProps: { region: "us_ct" },
        },
      );

      await waitFor(() => {
        expect(mockGetRateChanges).toHaveBeenCalledTimes(1);
      });

      rerender({ region: "us_ny" });

      await waitFor(() => {
        expect(mockGetRateChanges).toHaveBeenCalledTimes(2);
      });
    });

    it("handles fetch error", async () => {
      mockGetRateChanges.mockRejectedValue(new Error("Network error"));

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useRateChanges(), { wrapper });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe("Network error");
    });
  });

  // ==========================================================================
  // useAlertPreferences
  // ==========================================================================
  describe("useAlertPreferences", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetAlertPreferences.mockResolvedValue(mockPreferencesResponse);
    });

    it("fetches alert preferences", async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useAlertPreferences(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.preferences).toHaveLength(1);
      expect(mockGetAlertPreferences).toHaveBeenCalledTimes(1);
    });

    it("uses correct query key", async () => {
      const { wrapper, queryClient } = createWrapper();

      renderHook(() => useAlertPreferences(), { wrapper });

      await waitFor(() => {
        const queries = queryClient.getQueryCache().getAll();
        const keys = queries.map((q) => q.queryKey);
        expect(keys).toContainEqual(["alert-preferences"]);
      });
    });
  });

  // ==========================================================================
  // useUpsertAlertPreference
  // ==========================================================================
  describe("useUpsertAlertPreference", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockUpsertAlertPreference.mockResolvedValue({
        id: "pref-1",
        user_id: "user-1",
        utility_type: "electricity",
        enabled: false,
        channels: ["email"],
        cadence: "immediate",
        created_at: "2026-03-01T10:00:00Z",
        updated_at: "2026-03-16T10:00:00Z",
      });
    });

    it("upserts a preference and invalidates queries", async () => {
      const { wrapper, queryClient } = createWrapper();
      const invalidateSpy = jest.spyOn(queryClient, "invalidateQueries");

      const { result } = renderHook(() => useUpsertAlertPreference(), {
        wrapper,
      });

      await act(async () => {
        await result.current.mutateAsync({
          utility_type: "electricity",
          enabled: false,
        });
      });

      expect(mockUpsertAlertPreference).toHaveBeenCalledWith({
        utility_type: "electricity",
        enabled: false,
      });

      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["alert-preferences"] }),
      );
    });

    it("handles mutation failure", async () => {
      mockUpsertAlertPreference.mockRejectedValue(new Error("Unauthorized"));

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useUpsertAlertPreference(), {
        wrapper,
      });

      await expect(
        act(async () => {
          await result.current.mutateAsync({ utility_type: "electricity" });
        }),
      ).rejects.toThrow("Unauthorized");
    });
  });
}
