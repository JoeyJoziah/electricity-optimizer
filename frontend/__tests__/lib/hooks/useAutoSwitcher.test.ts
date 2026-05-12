import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetAutoSwitcherActivity = jest.fn();
const mockGetSettings = jest.fn();
const mockGetActivity = jest.fn();
const mockCheckNow = jest.fn();
const mockApproveSwitch = jest.fn();
const mockRollback = jest.fn();

jest.mock("@/lib/api/auto-switcher", () => ({
  getAutoSwitcherActivity: (...args: unknown[]) =>
    mockGetAutoSwitcherActivity(...args),
}));

jest.mock("@/lib/api/agent-switcher", () => ({
  getSettings: (...args: unknown[]) => mockGetSettings(...args),
  getActivity: (...args: unknown[]) => mockGetActivity(...args),
  checkNow: (...args: unknown[]) => mockCheckNow(...args),
  approveSwitch: (...args: unknown[]) => mockApproveSwitch(...args),
  rollback: (...args: unknown[]) => mockRollback(...args),
}));

import {
  autoSwitcherKeys,
  agentSwitcherKeys,
  useAutoSwitcherPendingCount,
  useCheckNow,
  useApproveSwitch,
  useRollback,
} from "@/lib/hooks/useAutoSwitcher";

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
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("autoSwitcherKeys", () => {
  it("has stable all key", () => {
    expect(autoSwitcherKeys.all).toEqual(["auto-switcher"]);
  });

  it("has stable activity key", () => {
    expect(autoSwitcherKeys.activity).toEqual(["auto-switcher", "activity"]);
  });

  it("has stable pendingCount key", () => {
    expect(autoSwitcherKeys.pendingCount).toEqual([
      "auto-switcher",
      "pending-count",
    ]);
  });
});

describe("agentSwitcherKeys", () => {
  it("has stable settings key", () => {
    expect(agentSwitcherKeys.settings).toEqual(["agent-switcher", "settings"]);
  });

  it("has stable activity key", () => {
    expect(agentSwitcherKeys.activity).toEqual(["agent-switcher", "activity"]);
  });
});

describe("useAutoSwitcherPendingCount", () => {
  beforeEach(() => mockGetAutoSwitcherActivity.mockReset());

  it("returns 0 when no recommend+unexecuted items", async () => {
    mockGetAutoSwitcherActivity.mockResolvedValue([
      { decision: "hold", executed: false },
      { decision: "recommend", executed: true },
    ]);
    const { result } = renderHook(() => useAutoSwitcherPendingCount(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe(0);
  });

  it("counts only recommend+unexecuted items", async () => {
    mockGetAutoSwitcherActivity.mockResolvedValue([
      { decision: "recommend", executed: false },
      { decision: "recommend", executed: false },
      { decision: "recommend", executed: true },
      { decision: "hold", executed: false },
    ]);
    const { result } = renderHook(() => useAutoSwitcherPendingCount(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe(2);
  });

  it("returns error state on fetch failure", async () => {
    mockGetAutoSwitcherActivity.mockRejectedValue(new Error("Network error"));
    const { result } = renderHook(() => useAutoSwitcherPendingCount(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useCheckNow", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useCheckNow(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });

  it("isPending starts as false", () => {
    const { result } = renderHook(() => useCheckNow(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isPending).toBe(false);
  });
});

describe("useApproveSwitch", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useApproveSwitch(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });
});

describe("useRollback", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useRollback(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });
});
