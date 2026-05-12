import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetForecast = jest.fn();
const mockGetForecastTypes = jest.fn();

jest.mock("@/lib/api/forecast", () => ({
  getForecast: (...args: unknown[]) => mockGetForecast(...args),
  getForecastTypes: (...args: unknown[]) => mockGetForecastTypes(...args),
}));

import { useForecast, useForecastTypes } from "@/lib/hooks/useForecast";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useForecast", () => {
  beforeEach(() => mockGetForecast.mockReset());

  it("is disabled when utilityType is undefined", () => {
    const { result } = renderHook(() => useForecast(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when utilityType is empty string", () => {
    const { result } = renderHook(() => useForecast(""), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when utilityType is provided", () => {
    mockGetForecast.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useForecast("electricity"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });

  it("passes utilityType, state, and horizonDays to API", () => {
    mockGetForecast.mockReturnValue(new Promise(() => {}));
    renderHook(() => useForecast("natural_gas", "CT", 14), {
      wrapper: makeWrapper(),
    });
    expect(mockGetForecast).toHaveBeenCalledWith(
      "natural_gas",
      "CT",
      14,
      expect.anything(),
    );
  });
});

describe("useForecastTypes", () => {
  beforeEach(() => mockGetForecastTypes.mockReset());

  it("fetches without any enabled condition", () => {
    mockGetForecastTypes.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useForecastTypes(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
