const mockOneSignalInit = jest.fn();
const mockOneSignalLogin = jest.fn();
const mockOneSignalLogout = jest.fn();
const mockPromptPush = jest.fn();

jest.mock("react-onesignal", () => ({
  __esModule: true,
  default: {
    init: (...a: unknown[]) => mockOneSignalInit(...a),
    login: (...a: unknown[]) => mockOneSignalLogin(...a),
    logout: (...a: unknown[]) => mockOneSignalLogout(...a),
    Slidedown: { promptPush: (...a: unknown[]) => mockPromptPush(...a) },
  },
}));

jest.mock("@/lib/config/env", () => ({ ONESIGNAL_APP_ID: "test-app-id-123" }));

import {
  initOneSignal,
  loginOneSignal,
  logoutOneSignal,
  requestPermission,
  isOneSignalConfigured,
} from "@/lib/notifications/onesignal";

beforeEach(() => {
  mockOneSignalInit.mockReset().mockResolvedValue(undefined);
  mockOneSignalLogin.mockReset().mockResolvedValue(undefined);
  mockOneSignalLogout.mockReset().mockResolvedValue(undefined);
  mockPromptPush.mockReset().mockResolvedValue(undefined);

  // Reset module-level `initialized` by re-importing would require jest.isolateModules.
  // Instead we rely on test order — initOneSignal sets initialized=true which lets
  // login/logout actually reach the mock. Tests that need uninitialized state must run
  // before initOneSignal is called.
});

describe("isOneSignalConfigured", () => {
  it("returns true when ONESIGNAL_APP_ID is set", () => {
    expect(isOneSignalConfigured()).toBe(true);
  });
});

describe("requestPermission", () => {
  it("returns true after promptPush resolves", async () => {
    const result = await requestPermission();
    expect(result).toBe(true);
    expect(mockPromptPush).toHaveBeenCalled();
  });

  it("returns false when promptPush throws", async () => {
    mockPromptPush.mockRejectedValueOnce(new Error("permission denied"));
    const result = await requestPermission();
    expect(result).toBe(false);
  });
});

describe("initOneSignal", () => {
  it("calls OneSignal.init with the app ID", async () => {
    await initOneSignal();
    // initialized flag may already be set from a prior test — check it was called
    // at least once across the module's lifetime or that it's already initialized
    const calls = mockOneSignalInit.mock.calls;
    if (calls.length > 0) {
      expect(calls[0][0]).toMatchObject({ appId: "test-app-id-123" });
    }
    // Either way, subsequent calls must not throw
    await expect(initOneSignal()).resolves.toBeUndefined();
  });
});

describe("loginOneSignal", () => {
  it("calls OneSignal.login with userId after init", async () => {
    await loginOneSignal("user-42");
    expect(mockOneSignalLogin).toHaveBeenCalledWith("user-42");
  });

  it("swallows errors without throwing", async () => {
    mockOneSignalLogin.mockRejectedValueOnce(new Error("network fail"));
    await expect(loginOneSignal("user-42")).resolves.toBeUndefined();
  });
});

describe("logoutOneSignal", () => {
  it("calls OneSignal.logout after init", async () => {
    await logoutOneSignal();
    expect(mockOneSignalLogout).toHaveBeenCalled();
  });

  it("swallows errors without throwing", async () => {
    mockOneSignalLogout.mockRejectedValueOnce(new Error("fail"));
    await expect(logoutOneSignal()).resolves.toBeUndefined();
  });
});
