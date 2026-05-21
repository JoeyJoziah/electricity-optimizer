import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetAlerts = jest.fn();
const mockGetAlertHistory = jest.fn();
const mockCreateAlert = jest.fn();
const mockUpdateAlert = jest.fn();
const mockDeleteAlert = jest.fn();

jest.mock("@/lib/api/alerts", () => ({
  getAlerts: (...args: unknown[]) => mockGetAlerts(...args),
  getAlertHistory: (...args: unknown[]) => mockGetAlertHistory(...args),
  createAlert: (...args: unknown[]) => mockCreateAlert(...args),
  updateAlert: (...args: unknown[]) => mockUpdateAlert(...args),
  deleteAlert: (...args: unknown[]) => mockDeleteAlert(...args),
}));

import {
  useAlerts,
  useAlertHistory,
  useCreateAlert,
  useUpdateAlert,
  useDeleteAlert,
} from "@/lib/hooks/useAlerts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestWrapper";
  return Wrapper;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useAlerts", () => {
  it("fetches alerts on mount", () => {
    mockGetAlerts.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAlerts(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
    expect(mockGetAlerts).toHaveBeenCalledTimes(1);
  });

  it("returns data on successful fetch", async () => {
    const alerts = [{ id: "a-1", region: "us_ct" }];
    mockGetAlerts.mockResolvedValue(alerts);
    const { result } = renderHook(() => useAlerts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(alerts);
  });

  it("returns error on failed fetch", async () => {
    mockGetAlerts.mockRejectedValue(new Error("fetch failed"));
    const { result } = renderHook(() => useAlerts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useAlertHistory", () => {
  it("includes page and pageSize in the queryFn call", () => {
    mockGetAlertHistory.mockReturnValue(new Promise(() => {}));
    renderHook(() => useAlertHistory(3, 10), { wrapper: makeWrapper() });
    expect(mockGetAlertHistory).toHaveBeenCalledWith(3, 10, expect.anything());
  });

  it("defaults to page 1 and pageSize 20", () => {
    mockGetAlertHistory.mockReturnValue(new Promise(() => {}));
    renderHook(() => useAlertHistory(), { wrapper: makeWrapper() });
    expect(mockGetAlertHistory).toHaveBeenCalledWith(1, 20, expect.anything());
  });
});

describe("useCreateAlert", () => {
  it("exposes isPending starting false", () => {
    const { result } = renderHook(() => useCreateAlert(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isPending).toBe(false);
  });

  it("calls createAlert API on mutate", async () => {
    mockCreateAlert.mockResolvedValue({ id: "new-alert" });
    const { result } = renderHook(() => useCreateAlert(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate({
        region: "us_ct",
        threshold_type: "above",
      } as Parameters<typeof result.current.mutate>[0]);
    });
    expect(mockCreateAlert).toHaveBeenCalledTimes(1);
  });
});

describe("useUpdateAlert", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useUpdateAlert(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });
});

describe("useDeleteAlert", () => {
  it("calls deleteAlert API on mutate", async () => {
    mockDeleteAlert.mockResolvedValue(undefined);
    const { result } = renderHook(() => useDeleteAlert(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate("alert-99");
    });
    expect(mockDeleteAlert).toHaveBeenCalledWith("alert-99");
  });
});
