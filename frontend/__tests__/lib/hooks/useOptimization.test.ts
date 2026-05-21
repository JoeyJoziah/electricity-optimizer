import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetOptimalSchedule = jest.fn();
const mockGetOptimizationResult = jest.fn();
const mockGetAppliances = jest.fn();
const mockSaveAppliances = jest.fn();
const mockCalculatePotentialSavings = jest.fn();

jest.mock("@/lib/api/optimization", () => ({
  getOptimalSchedule: (...args: unknown[]) => mockGetOptimalSchedule(...args),
  getOptimizationResult: (...args: unknown[]) =>
    mockGetOptimizationResult(...args),
  getAppliances: (...args: unknown[]) => mockGetAppliances(...args),
  saveAppliances: (...args: unknown[]) => mockSaveAppliances(...args),
  calculatePotentialSavings: (...args: unknown[]) =>
    mockCalculatePotentialSavings(...args),
}));

import {
  useOptimalSchedule,
  useOptimizationResult,
  useSavedAppliances,
  useSaveAppliances,
  usePotentialSavings,
} from "@/lib/hooks/useOptimization";
import type { Appliance } from "@/types";

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

const mockAppliance: Appliance = {
  id: "app-1",
  name: "Washer",
  watts: 500,
  hoursPerDay: 1,
  category: "laundry",
} as Appliance;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useOptimalSchedule", () => {
  it("is disabled when appliances array is empty", () => {
    const { result } = renderHook(
      () => useOptimalSchedule({ appliances: [], region: "us_ct" }),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when appliances are present", () => {
    mockGetOptimalSchedule.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () =>
        useOptimalSchedule({ appliances: [mockAppliance], region: "us_ct" }),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useOptimizationResult", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(
      () => useOptimizationResult("2025-01-01", null),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when date and region are provided", () => {
    mockGetOptimizationResult.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () => useOptimizationResult("2025-01-01", "us_ct"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useSavedAppliances", () => {
  it("fetches on mount", () => {
    mockGetAppliances.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useSavedAppliances(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useSaveAppliances", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useSaveAppliances(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });
});

describe("usePotentialSavings", () => {
  it("is disabled when appliances array is empty", () => {
    const { result } = renderHook(() => usePotentialSavings([], "us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when region is null", () => {
    const { result } = renderHook(
      () => usePotentialSavings([mockAppliance], null),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled with appliances and region", () => {
    mockCalculatePotentialSavings.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () => usePotentialSavings([mockAppliance], "us_ct"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
