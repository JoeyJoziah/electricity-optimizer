import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockDetectCCA = jest.fn();
const mockCompareCCARate = jest.fn();
const mockGetCCAInfo = jest.fn();
const mockListCCAPrograms = jest.fn();

jest.mock("@/lib/api/cca", () => ({
  detectCCA: (...args: unknown[]) => mockDetectCCA(...args),
  compareCCARate: (...args: unknown[]) => mockCompareCCARate(...args),
  getCCAInfo: (...args: unknown[]) => mockGetCCAInfo(...args),
  listCCAPrograms: (...args: unknown[]) => mockListCCAPrograms(...args),
}));

import {
  useCCADetect,
  useCCACompare,
  useCCAInfo,
  useCCAPrograms,
} from "@/lib/hooks/useCCA";

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

describe("useCCADetect", () => {
  it("is disabled when both zipCode and state are undefined", () => {
    const { result } = renderHook(() => useCCADetect(undefined, undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when zipCode is provided", () => {
    mockDetectCCA.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCCADetect("06001"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });

  it("is enabled when state is provided", () => {
    mockDetectCCA.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCCADetect(undefined, "CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useCCACompare", () => {
  it("is disabled when ccaId is undefined", () => {
    const { result } = renderHook(() => useCCACompare(undefined, 0.22), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when defaultRate is 0", () => {
    const { result } = renderHook(() => useCCACompare("cca-1", 0), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when ccaId and positive defaultRate are provided", () => {
    mockCompareCCARate.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCCACompare("cca-1", 0.22), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useCCAInfo", () => {
  it("is disabled when ccaId is undefined", () => {
    const { result } = renderHook(() => useCCAInfo(undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when ccaId is provided", () => {
    mockGetCCAInfo.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCCAInfo("cca-1"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useCCAPrograms", () => {
  it("fetches on mount (no enabled condition)", () => {
    mockListCCAPrograms.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCCAPrograms(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
