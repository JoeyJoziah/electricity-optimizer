import {
  getSettings,
  updateSettings,
  signLOA,
  revokeLOA,
  getHistory,
  getActivity,
  checkNow,
  rollback,
  approveSwitch,
} from "@/lib/api/agent-switcher";
import { _resetRedirectState } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>;

function mockJson(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: jest.fn().mockResolvedValue(body),
    headers: new Headers(),
    redirected: false,
    type: "basic",
    url: "",
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
    text: jest.fn(),
    bytes: jest.fn(),
  } as unknown as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

// ---------------------------------------------------------------------------
// getSettings
// ---------------------------------------------------------------------------

describe("getSettings", () => {
  it("calls GET /agent-switcher/settings", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        enabled: true,
        paused_until: null,
        loa_signed: false,
        loa_revoked: false,
        savings_threshold_pct: 10,
        savings_threshold_min: 5,
        cooldown_days: 5,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }),
    );
    await getSettings();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/settings");
    expect(mockFetch.mock.calls[0]![1]?.method ?? "GET").toBe("GET");
  });
});

// ---------------------------------------------------------------------------
// updateSettings
// ---------------------------------------------------------------------------

describe("updateSettings", () => {
  it("calls PUT /agent-switcher/settings with payload", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        enabled: false,
        paused_until: null,
        loa_signed: false,
        loa_revoked: false,
        savings_threshold_pct: 10,
        savings_threshold_min: 5,
        cooldown_days: 7,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-02T00:00:00Z",
      }),
    );
    await updateSettings({ enabled: false, cooldown_days: 7 });
    const call = mockFetch.mock.calls[0]!;
    const url = call[0] as string;
    expect(url).toContain("/agent-switcher/settings");
    expect(call[1]?.method).toBe("PUT");
  });
});

// ---------------------------------------------------------------------------
// signLOA / revokeLOA
// ---------------------------------------------------------------------------

describe("signLOA", () => {
  it("calls POST /agent-switcher/loa/sign", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ message: "LOA signed", signed_at: "2026-05-12T00:00:00Z" }),
    );
    await signLOA();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/loa/sign");
    expect(mockFetch.mock.calls[0]![1]?.method).toBe("POST");
  });
});

describe("revokeLOA", () => {
  it("calls POST /agent-switcher/loa/revoke", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ message: "LOA revoked", revoked_at: "2026-05-12T00:00:00Z" }),
    );
    await revokeLOA();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/loa/revoke");
  });
});

// ---------------------------------------------------------------------------
// getHistory — wraps res.history with ?? [] fallback
// ---------------------------------------------------------------------------

describe("getHistory", () => {
  it("calls GET /agent-switcher/history", async () => {
    mockFetch.mockResolvedValue(mockJson({ history: [], total: 0 }));
    await getHistory();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/history");
  });

  it("passes limit and offset params", async () => {
    mockFetch.mockResolvedValue(mockJson({ history: [], total: 0 }));
    await getHistory(50, 100);
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("limit=50");
    expect(url).toContain("offset=100");
  });

  it("returns history array from response", async () => {
    const entry = {
      id: "entry-1",
      trigger_type: "scheduled",
      decision: "hold",
      reason: "Rates competitive",
      current_plan_name: "PlanA",
      proposed_plan_name: null,
      savings_monthly: null,
      savings_annual: null,
      etf_cost: 0,
      net_savings_year1: null,
      confidence_score: 0.9,
      tier: "pro",
      executed: false,
      created_at: "2026-05-12T00:00:00Z",
    };
    mockFetch.mockResolvedValue(mockJson({ history: [entry], total: 1 }));
    const result = await getHistory();
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("entry-1");
  });

  it("falls back to empty array when history is null", async () => {
    mockFetch.mockResolvedValue(mockJson({ history: null, total: 0 }));
    const result = await getHistory();
    expect(result).toEqual([]);
  });

  it("falls back to empty array when history is undefined", async () => {
    mockFetch.mockResolvedValue(mockJson({ total: 0 }));
    const result = await getHistory();
    expect(result).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// getActivity — wraps res.activity with ?? [] fallback
// ---------------------------------------------------------------------------

describe("getActivity", () => {
  it("calls GET /agent-switcher/activity", async () => {
    mockFetch.mockResolvedValue(mockJson({ activity: [], total: 0 }));
    await getActivity();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/activity");
  });

  it("returns activity array from response", async () => {
    const act = {
      id: "act-1",
      trigger_type: "on_demand",
      decision: "switch",
      reason: "Cheap new plan",
      current_plan_name: "OldPlan",
      proposed_plan_name: "NewPlan",
      savings_monthly: 15,
      savings_annual: 180,
      etf_cost: 0,
      net_savings_year1: 180,
      confidence_score: 0.95,
      tier: "pro",
      executed: true,
      created_at: "2026-05-12T00:00:00Z",
    };
    mockFetch.mockResolvedValue(mockJson({ activity: [act], total: 1 }));
    const result = await getActivity();
    expect(result).toHaveLength(1);
    expect(result[0].decision).toBe("switch");
  });

  it("falls back to empty array when activity is null", async () => {
    mockFetch.mockResolvedValue(mockJson({ activity: null, total: 0 }));
    const result = await getActivity();
    expect(result).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// checkNow
// ---------------------------------------------------------------------------

describe("checkNow", () => {
  it("calls POST /agent-switcher/check", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        action: "hold",
        reason: "Rates competitive",
        current_plan: null,
        proposed_plan: null,
        projected_savings_monthly: 0,
        projected_savings_annual: 0,
        etf_cost: 0,
        net_savings_year1: 0,
        confidence: 0.8,
        contract_expiring_soon: false,
        data_source: "market",
      }),
    );
    const result = await checkNow();
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/check");
    expect(mockFetch.mock.calls[0]![1]?.method).toBe("POST");
    expect(result.action).toBe("hold");
  });
});

// ---------------------------------------------------------------------------
// rollback
// ---------------------------------------------------------------------------

describe("rollback", () => {
  it("calls POST /agent-switcher/executions/{id}/rollback", async () => {
    mockFetch.mockResolvedValue(
      mockJson({ status: "rolled_back", message: "Switch reversed." }),
    );
    await rollback("exec-abc");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/executions/exec-abc/rollback");
    expect(mockFetch.mock.calls[0]![1]?.method).toBe("POST");
  });
});

// ---------------------------------------------------------------------------
// approveSwitch
// ---------------------------------------------------------------------------

describe("approveSwitch", () => {
  it("calls POST /agent-switcher/audit/{id}/approve", async () => {
    mockFetch.mockResolvedValue(
      mockJson({
        id: "exec-1",
        status: "initiated",
        enrollment_id: null,
        old_plan_name: "OldPlan",
        new_plan_name: "NewPlan",
        initiated_at: "2026-05-12T00:00:00Z",
        confirmed_at: null,
        enacted_at: null,
        rescission_ends: null,
        failure_reason: null,
        created_at: "2026-05-12T00:00:00Z",
      }),
    );
    const result = await approveSwitch("audit-xyz");
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("/agent-switcher/audit/audit-xyz/approve");
    expect(mockFetch.mock.calls[0]![1]?.method).toBe("POST");
    expect(result.status).toBe("initiated");
  });
});
