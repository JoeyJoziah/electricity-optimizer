/**
 * useGA4Event Hook Tests
 *
 * TDD: tests written before implementation.
 * Covers: hook return value, window.gtag calls, no-op safety.
 */

import { renderHook, act } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Type augmentation for window.gtag
// ---------------------------------------------------------------------------

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
    dataLayer?: unknown[];
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useGA4Event hook", () => {
  beforeEach(() => {
    // Clean slate for each test
    delete window.gtag;
    delete window.dataLayer;
  });

  it("returns a trackEvent function", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useGA4Event } = require("@/lib/analytics/useGA4Event");
    const { result } = renderHook(() => useGA4Event());
    expect(typeof result.current.trackEvent).toBe("function");
  });

  it("calls window.gtag with event name and params when gtag is defined", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useGA4Event } = require("@/lib/analytics/useGA4Event");
    const mockGtag = jest.fn();
    window.gtag = mockGtag;

    const { result } = renderHook(() => useGA4Event());

    act(() => {
      result.current.trackEvent("signup", { method: "email" });
    });

    expect(mockGtag).toHaveBeenCalledWith("event", "signup", {
      method: "email",
    });
  });

  it("calls window.gtag without params when none provided", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useGA4Event } = require("@/lib/analytics/useGA4Event");
    const mockGtag = jest.fn();
    window.gtag = mockGtag;

    const { result } = renderHook(() => useGA4Event());

    act(() => {
      result.current.trackEvent("login");
    });

    expect(mockGtag).toHaveBeenCalledWith("event", "login", undefined);
  });

  it("is a no-op (does not throw) when window.gtag is not defined", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useGA4Event } = require("@/lib/analytics/useGA4Event");
    // Ensure gtag is absent
    delete window.gtag;

    const { result } = renderHook(() => useGA4Event());

    expect(() => {
      act(() => {
        result.current.trackEvent("forecast_view");
      });
    }).not.toThrow();
  });

  it("supports all documented event names without TypeScript errors at runtime", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useGA4Event } = require("@/lib/analytics/useGA4Event");
    const mockGtag = jest.fn();
    window.gtag = mockGtag;

    const { result } = renderHook(() => useGA4Event());

    const events = [
      "signup",
      "login",
      "forecast_view",
      "switch_initiated",
      "plan_upgrade",
      "connection_added",
    ] as const;

    act(() => {
      events.forEach((name) => result.current.trackEvent(name));
    });

    expect(mockGtag).toHaveBeenCalledTimes(events.length);
  });

  it("passes arbitrary extra params through to gtag", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useGA4Event } = require("@/lib/analytics/useGA4Event");
    const mockGtag = jest.fn();
    window.gtag = mockGtag;

    const { result } = renderHook(() => useGA4Event());

    const params = { plan: "pro", region: "TX", value: 4.99 };

    act(() => {
      result.current.trackEvent("plan_upgrade", params);
    });

    expect(mockGtag).toHaveBeenCalledWith("event", "plan_upgrade", params);
  });
});
