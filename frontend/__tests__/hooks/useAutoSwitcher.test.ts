import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useAutoSwitcherActivity,
  useAutoSwitcherPendingCount,
  useAgentSettings,
  useAgentActivity,
  useCheckNow,
  useApproveSwitch,
  useRollback,
  autoSwitcherKeys,
  agentSwitcherKeys,
} from "@/lib/hooks/useAutoSwitcher";

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
  checkNow: () => mockCheckNow(),
  approveSwitch: (id: string) => mockApproveSwitch(id),
  rollback: (id: string) => mockRollback(id),
}));

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

const _activity = [
  {
    id: "a-1",
    decision: "recommend",
    executed: false,
    created_at: "2026-05-12T00:00:00Z",
  },
  {
    id: "a-2",
    decision: "switch",
    executed: true,
    created_at: "2026-05-11T00:00:00Z",
  },
];

const _settings = {
  enabled: true,
  paused_until: null,
  loa_signed: true,
  loa_revoked: false,
  savings_threshold_pct: 10,
  savings_threshold_min: 5,
  cooldown_days: 5,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// autoSwitcherKeys / agentSwitcherKeys
// ---------------------------------------------------------------------------

describe("query key constants", () => {
  it("autoSwitcherKeys.activity has correct shape", () => {
    expect(autoSwitcherKeys.activity).toEqual(["auto-switcher", "activity"]);
    expect(autoSwitcherKeys.pendingCount).toEqual([
      "auto-switcher",
      "pending-count",
    ]);
  });

  it("agentSwitcherKeys has settings, activity, history keys", () => {
    expect(agentSwitcherKeys.settings).toEqual(["agent-switcher", "settings"]);
    expect(agentSwitcherKeys.activity).toEqual(["agent-switcher", "activity"]);
    expect(agentSwitcherKeys.history).toEqual(["agent-switcher", "history"]);
  });
});

// ---------------------------------------------------------------------------
// useAutoSwitcherActivity
// ---------------------------------------------------------------------------

describe("useAutoSwitcherActivity", () => {
  it("fetches activity via getAutoSwitcherActivity(10)", async () => {
    mockGetAutoSwitcherActivity.mockResolvedValue(_activity);
    const { result } = renderHook(() => useAutoSwitcherActivity(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAutoSwitcherActivity).toHaveBeenCalledWith(
      10,
      expect.anything(),
    );
    expect(result.current.data).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// useAutoSwitcherPendingCount
// ---------------------------------------------------------------------------

describe("useAutoSwitcherPendingCount", () => {
  it("counts unexecuted recommend entries", async () => {
    mockGetAutoSwitcherActivity.mockResolvedValue(_activity);
    const { result } = renderHook(() => useAutoSwitcherPendingCount(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // Only 'a-1' matches decision=recommend + executed=false
    expect(result.current.data).toBe(1);
  });

  it("returns 0 when all recommendations are executed", async () => {
    mockGetAutoSwitcherActivity.mockResolvedValue([
      {
        id: "a-3",
        decision: "recommend",
        executed: true,
        created_at: "2026-05-10T00:00:00Z",
      },
    ]);
    const { result } = renderHook(() => useAutoSwitcherPendingCount(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe(0);
  });

  it("returns 0 when activity list is empty", async () => {
    mockGetAutoSwitcherActivity.mockResolvedValue([]);
    const { result } = renderHook(() => useAutoSwitcherPendingCount(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// useAgentSettings
// ---------------------------------------------------------------------------

describe("useAgentSettings", () => {
  it("fetches settings", async () => {
    mockGetSettings.mockResolvedValue(_settings);
    const { result } = renderHook(() => useAgentSettings(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.enabled).toBe(true);
    expect(result.current.data!.loa_signed).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// useAgentActivity
// ---------------------------------------------------------------------------

describe("useAgentActivity", () => {
  it("fetches activity with default limit 10", async () => {
    mockGetActivity.mockResolvedValue(_activity);
    const { result } = renderHook(() => useAgentActivity(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetActivity).toHaveBeenCalledWith(10, expect.anything());
  });

  it("passes custom limit", async () => {
    mockGetActivity.mockResolvedValue(_activity);
    const { result } = renderHook(() => useAgentActivity(25), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetActivity).toHaveBeenCalledWith(25, expect.anything());
  });
});

// ---------------------------------------------------------------------------
// useCheckNow
// ---------------------------------------------------------------------------

describe("useCheckNow", () => {
  it("calls checkNow() and succeeds", async () => {
    const decision = {
      action: "hold",
      reason: "Rates competitive",
      confidence: 0.9,
    };
    mockCheckNow.mockResolvedValue(decision);
    mockGetActivity.mockResolvedValue([]);
    const { result } = renderHook(() => useCheckNow(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate(undefined);
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCheckNow).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// useApproveSwitch
// ---------------------------------------------------------------------------

describe("useApproveSwitch", () => {
  it("calls approveSwitch with auditLogId", async () => {
    const execution = {
      id: "exec-1",
      status: "initiated",
      old_plan_name: "PlanA",
      new_plan_name: "PlanB",
    };
    mockApproveSwitch.mockResolvedValue(execution);
    mockGetActivity.mockResolvedValue([]);
    const { result } = renderHook(() => useApproveSwitch(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate("audit-xyz");
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApproveSwitch).toHaveBeenCalledWith("audit-xyz");
  });
});

// ---------------------------------------------------------------------------
// useRollback
// ---------------------------------------------------------------------------

describe("useRollback", () => {
  it("calls rollback with executionId", async () => {
    mockRollback.mockResolvedValue({
      status: "rolled_back",
      message: "Reversed.",
    });
    mockGetActivity.mockResolvedValue([]);
    const { result } = renderHook(() => useRollback(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate("exec-abc");
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockRollback).toHaveBeenCalledWith("exec-abc");
  });
});
