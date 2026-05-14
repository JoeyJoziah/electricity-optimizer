// AuthProvider branch coverage tests

jest.mock("@/lib/auth/client", () => ({
  authClient: {
    signIn: { email: jest.fn(), social: jest.fn(), magicLink: jest.fn() },
    signOut: jest.fn(),
    signUp: { email: jest.fn() },
    getSession: jest.fn(),
    useSession: jest.fn(),
  },
}));

const mockPush = jest.fn();
const mockReplace = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

const mockGetUserSupplier = jest.fn();
const mockGetUserProfile = jest.fn();
const mockUpdateUserProfile = jest.fn();

jest.mock("@/lib/api/suppliers", () => ({
  getUserSupplier: (...a: unknown[]) => mockGetUserSupplier(...a),
}));
jest.mock("@/lib/api/profile", () => ({
  getUserProfile: (...a: unknown[]) => mockGetUserProfile(...a),
  updateUserProfile: (...a: unknown[]) => mockUpdateUserProfile(...a),
}));

const mockSetRegion = jest.fn();
const mockSetCurrentSupplier = jest.fn();
const mockResetSettings = jest.fn();

jest.mock("@/lib/store/settings", () => {
  const mock = jest.fn(() => ({ setRegion: mockSetRegion, region: undefined }));
  (mock as unknown as Record<string, unknown>).getState = jest.fn(() => ({
    setCurrentSupplier: mockSetCurrentSupplier,
    setRegion: mockSetRegion,
    resetSettings: mockResetSettings,
    region: undefined,
  }));
  return { useSettingsStore: mock };
});

jest.mock("@/lib/config/env", () => ({ API_URL: "https://api.test.invalid" }));

const mockLoginOneSignal = jest.fn();
const mockLogoutOneSignal = jest.fn();

jest.mock("@/lib/notifications/onesignal", () => ({
  loginOneSignal: (...a: unknown[]) => mockLoginOneSignal(...a),
  logoutOneSignal: (...a: unknown[]) => mockLogoutOneSignal(...a),
}));

jest.mock("@/lib/utils/url", () => ({
  isSafeRedirect: (url: string) => url.startsWith("/"),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import React from "react";
import { act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { renderHook } from "@testing-library/react";
import { AuthProvider, useAuth } from "@/lib/hooks/useAuth";

const { authClient: mockAuthClient } = jest.requireMock("@/lib/auth/client");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

/** Helper: run an async fn inside act(), catching thrown errors so act() completes state updates */
async function runInAct<T>(
  fn: () => Promise<T>,
): Promise<{ result?: T; error?: Error }> {
  let result: T | undefined;
  let error: Error | undefined;
  await act(async () => {
    try {
      result = await fn();
    } catch (e) {
      error = e as Error;
    }
  });
  return { result, error };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  jest.clearAllMocks();
  // Restore fetch mock so .catch() works
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: jest.fn() });
  // Default: no session
  mockAuthClient.getSession.mockResolvedValue({ data: null });
  mockGetUserSupplier.mockResolvedValue({ supplier: null });
  mockGetUserProfile.mockResolvedValue({
    region: "us_ct",
    onboarding_completed: true,
  });
  // Restore getState on useSettingsStore mock
  const { useSettingsStore } = jest.requireMock("@/lib/store/settings");
  useSettingsStore.getState = jest.fn(() => ({
    setCurrentSupplier: mockSetCurrentSupplier,
    setRegion: mockSetRegion,
    resetSettings: mockResetSettings,
    region: undefined,
  }));
  // Mock window.location with proper setter
  let _href = "http://localhost:3000/dashboard";
  Object.defineProperty(window, "location", {
    writable: true,
    value: {
      pathname: "/dashboard",
      search: "",
      get href() {
        return _href;
      },
      set href(v: string) {
        _href = v;
      },
    },
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AuthProvider — initial state", () => {
  it("starts unauthenticated when no session", async () => {
    mockAuthClient.getSession.mockResolvedValue({ data: null });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
  });

  it("sets user from session when session exists", async () => {
    mockAuthClient.getSession.mockResolvedValue({
      data: {
        user: {
          id: "user-1",
          email: "test@test.com",
          name: "Test User",
          emailVerified: true,
          createdAt: new Date().toISOString(),
        },
      },
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => {
      expect(result.current.user?.email).toBe("test@test.com");
    });
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("calls loginOneSignal when session found", async () => {
    mockAuthClient.getSession.mockResolvedValue({
      data: {
        user: {
          id: "user-99",
          email: "x@x.com",
          name: null,
          emailVerified: false,
          createdAt: new Date().toISOString(),
        },
      },
    });
    renderHook(() => useAuth(), { wrapper });
    await waitFor(() => {
      expect(mockLoginOneSignal).toHaveBeenCalledWith("user-99");
    });
  });

  it("handles session fetch rejection gracefully", async () => {
    mockAuthClient.getSession.mockRejectedValue(new Error("Network error"));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.user).toBeNull();
  });
});

describe("AuthProvider — signIn", () => {
  it("sets user on successful sign in", async () => {
    mockAuthClient.signIn.email.mockResolvedValue({
      data: {
        user: {
          id: "user-2",
          email: "user@example.com",
          name: "User",
          emailVerified: true,
          createdAt: new Date().toISOString(),
        },
      },
      error: null,
    });
    Object.defineProperty(window.location, "href", {
      writable: true,
      value: "",
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await runInAct(async () => {
      await result.current.signIn("user@example.com", "password");
    });
    expect(mockLoginOneSignal).toHaveBeenCalledWith("user-2");
  });

  it("sets error on failed sign in", async () => {
    mockAuthClient.signIn.email.mockResolvedValue({
      data: null,
      error: { message: "Invalid credentials" },
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const { error } = await runInAct(async () => {
      await result.current.signIn("bad@example.com", "wrong");
    });
    expect(error?.message).toBe("Invalid credentials");
    await waitFor(() => {
      expect(result.current.error).toBe("Invalid credentials");
    });
  });

  it("uses generic message when authError has no message", async () => {
    mockAuthClient.signIn.email.mockResolvedValue({
      data: null,
      error: {},
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const { error } = await runInAct(async () => {
      await result.current.signIn("bad@example.com", "wrong");
    });
    expect(error?.message).toBe("Failed to sign in");
  });

  it("uses /dashboard as fallback when no callbackUrl", async () => {
    mockAuthClient.signIn.email.mockResolvedValue({
      data: {
        user: {
          id: "u",
          email: "a@a.com",
          emailVerified: false,
          createdAt: "",
        },
      },
      error: null,
    });
    const hrefSpy = jest
      .spyOn(window.location, "href", "set")
      .mockImplementation(() => {});

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.signIn("a@a.com", "pass");
    });
    expect(hrefSpy).toHaveBeenCalledWith("/dashboard");
    hrefSpy.mockRestore();
  });
});

describe("AuthProvider — signUp", () => {
  it("redirects to verify-email on successful sign up", async () => {
    mockAuthClient.signUp.email.mockResolvedValue({ error: null });
    const hrefSpy = jest
      .spyOn(window.location, "href", "set")
      .mockImplementation(() => {});

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.signUp("new@example.com", "password123", "Name");
    });
    expect(hrefSpy).toHaveBeenCalledWith(
      expect.stringContaining("/auth/verify-email"),
    );
    hrefSpy.mockRestore();
  });

  it("passes turnstile token header when provided", async () => {
    mockAuthClient.signUp.email.mockResolvedValue({ error: null });
    jest.spyOn(window.location, "href", "set").mockImplementation(() => {});

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.signUp("new@example.com", "pass", "Name", {
        turnstileToken: "tok-abc",
      });
    });
    expect(mockAuthClient.signUp.email).toHaveBeenCalledWith(
      expect.objectContaining({ email: "new@example.com" }),
      expect.objectContaining({ headers: { "X-Turnstile-Token": "tok-abc" } }),
    );
  });

  it("signs up without options (no turnstile token)", async () => {
    mockAuthClient.signUp.email.mockResolvedValue({ error: null });
    jest.spyOn(window.location, "href", "set").mockImplementation(() => {});

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.signUp("new@example.com", "pass");
    });
    // Called with single argument (no options)
    expect(mockAuthClient.signUp.email).toHaveBeenCalledTimes(1);
    expect(mockAuthClient.signUp.email.mock.calls[0].length).toBe(1);
  });

  it("sets error on failed sign up", async () => {
    mockAuthClient.signUp.email.mockResolvedValue({
      error: { message: "Email already in use" },
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const { error } = await runInAct(async () => {
      await result.current.signUp("dup@example.com", "pass");
    });
    expect(error?.message).toBe("Email already in use");
    await waitFor(() => {
      expect(result.current.error).toBe("Email already in use");
    });
  });
});

describe("AuthProvider — signOut", () => {
  it("calls logoutOneSignal and resetSettings", async () => {
    mockAuthClient.signOut.mockResolvedValue(undefined);
    jest.spyOn(window.location, "href", "set").mockImplementation(() => {});

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.signOut();
    });
    expect(mockLogoutOneSignal).toHaveBeenCalled();
    expect(mockResetSettings).toHaveBeenCalled();
  });

  it("proceeds and clears state even when signOut throws", async () => {
    mockAuthClient.signOut.mockRejectedValue(new Error("auth error"));
    jest.spyOn(window.location, "href", "set").mockImplementation(() => {});

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.signOut();
    });
    expect(mockResetSettings).toHaveBeenCalled();
  });
});

describe("AuthProvider — social sign in", () => {
  it("calls signIn.social with google provider", async () => {
    mockAuthClient.signIn.social.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.signInWithGoogle();
    });
    expect(mockAuthClient.signIn.social).toHaveBeenCalledWith(
      expect.objectContaining({ provider: "google" }),
    );
  });

  it("sets error when google sign in throws", async () => {
    mockAuthClient.signIn.social.mockRejectedValue(new Error("popup blocked"));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const { error } = await runInAct(async () => {
      await result.current.signInWithGoogle();
    });
    expect(error?.message).toBe("popup blocked");
    await waitFor(() => expect(result.current.error).toBe("popup blocked"));
  });

  it("calls signIn.social with github provider", async () => {
    mockAuthClient.signIn.social.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.signInWithGitHub();
    });
    expect(mockAuthClient.signIn.social).toHaveBeenCalledWith(
      expect.objectContaining({ provider: "github" }),
    );
  });

  it("uses fallback message when github error is not an Error instance", async () => {
    mockAuthClient.signIn.social.mockRejectedValue("string error");

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await runInAct(async () => {
      await result.current.signInWithGitHub();
    });
    await waitFor(() => {
      expect(result.current.error).toBe("Failed to sign in with GitHub");
    });
  });
});

describe("AuthProvider — sendMagicLink", () => {
  it("calls authClient.signIn.magicLink", async () => {
    mockAuthClient.signIn.magicLink.mockResolvedValue({ error: null });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await runInAct(async () => {
      await result.current.sendMagicLink("user@example.com");
    });
    expect(mockAuthClient.signIn.magicLink).toHaveBeenCalledWith(
      expect.objectContaining({ email: "user@example.com" }),
    );
  });

  it("sets error when magic link auth returns an error", async () => {
    mockAuthClient.signIn.magicLink.mockResolvedValue({
      error: { message: "Invalid email" },
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const { error } = await runInAct(async () => {
      await result.current.sendMagicLink("bad@example.com");
    });
    expect(error?.message).toBe("Invalid email");
    await waitFor(() => expect(result.current.error).toBe("Invalid email"));
  });

  it("uses fallback message when magic link error has no message", async () => {
    mockAuthClient.signIn.magicLink.mockResolvedValue({ error: {} });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const { error } = await runInAct(async () => {
      await result.current.sendMagicLink("user@example.com");
    });
    expect(error?.message).toBe("Failed to send magic link");
  });
});

describe("AuthProvider — clearError", () => {
  it("clears the error state", async () => {
    mockAuthClient.signIn.email.mockResolvedValue({
      data: null,
      error: { message: "Bad password" },
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await runInAct(async () => {
      await result.current.signIn("a@b.com", "wrong");
    });
    await waitFor(() => expect(result.current.error).toBe("Bad password"));

    act(() => result.current.clearError());
    await waitFor(() => expect(result.current.error).toBeNull());
  });
});

describe("useAuth — outside provider", () => {
  it("throws when used outside AuthProvider", () => {
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(
      "useAuth must be used within an AuthProvider",
    );
    spy.mockRestore();
  });
});
