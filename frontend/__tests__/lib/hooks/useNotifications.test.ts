import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetNotifications = jest.fn();
const mockGetNotificationCount = jest.fn();
const mockMarkNotificationRead = jest.fn();
const mockMarkAllRead = jest.fn();

jest.mock("@/lib/api/notifications", () => ({
  getNotifications: (...args: unknown[]) => mockGetNotifications(...args),
  getNotificationCount: (...args: unknown[]) =>
    mockGetNotificationCount(...args),
  markNotificationRead: (...args: unknown[]) =>
    mockMarkNotificationRead(...args),
  markAllRead: (...args: unknown[]) => mockMarkAllRead(...args),
}));

import {
  notificationKeys,
  useNotifications,
  useNotificationCount,
  useMarkRead,
  useMarkAllRead,
} from "@/lib/hooks/useNotifications";

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

describe("notificationKeys", () => {
  it("has stable all key", () => {
    expect(notificationKeys.all).toEqual(["notifications"]);
  });

  it("has stable count key", () => {
    expect(notificationKeys.count).toEqual(["notifications", "count"]);
  });
});

describe("useNotifications", () => {
  it("fetches on mount", () => {
    mockGetNotifications.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useNotifications(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useNotificationCount", () => {
  it("fetches on mount", () => {
    mockGetNotificationCount.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useNotificationCount(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useMarkRead", () => {
  it("calls markNotificationRead with id", async () => {
    mockMarkNotificationRead.mockResolvedValue(undefined);
    const { result } = renderHook(() => useMarkRead(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate("notif-42");
    });
    expect(mockMarkNotificationRead).toHaveBeenCalledWith("notif-42");
  });
});

describe("useMarkAllRead", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useMarkAllRead(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });

  it("calls markAllRead on mutate", async () => {
    mockMarkAllRead.mockResolvedValue(undefined);
    const { result } = renderHook(() => useMarkAllRead(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate();
    });
    expect(mockMarkAllRead).toHaveBeenCalledTimes(1);
  });
});
