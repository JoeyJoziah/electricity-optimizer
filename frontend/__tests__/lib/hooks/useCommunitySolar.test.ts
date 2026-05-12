import { renderHook } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetCommunitySolarPrograms = jest.fn();
const mockGetCommunitySolarSavings = jest.fn();
const mockGetCommunitySolarProgram = jest.fn();
const mockGetCommunitySolarStates = jest.fn();

jest.mock("@/lib/api/community-solar", () => ({
  getCommunitySolarPrograms: (...args: unknown[]) =>
    mockGetCommunitySolarPrograms(...args),
  getCommunitySolarSavings: (...args: unknown[]) =>
    mockGetCommunitySolarSavings(...args),
  getCommunitySolarProgram: (...args: unknown[]) =>
    mockGetCommunitySolarProgram(...args),
  getCommunitySolarStates: (...args: unknown[]) =>
    mockGetCommunitySolarStates(...args),
}));

import {
  MAX_MONTHLY_BILL,
  MAX_SAVINGS_PERCENT,
  isValidNumericInput,
  useCommunitySolarPrograms,
  useCommunitySolarSavings,
  useCommunitySolarProgram,
  useCommunitySolarStates,
} from "@/lib/hooks/useCommunitySolar";

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

describe("constants", () => {
  it("MAX_MONTHLY_BILL is 50000", () => {
    expect(MAX_MONTHLY_BILL).toBe(50_000);
  });

  it("MAX_SAVINGS_PERCENT is 100", () => {
    expect(MAX_SAVINGS_PERCENT).toBe(100);
  });
});

describe("isValidNumericInput", () => {
  it("returns false for null", () => {
    expect(isValidNumericInput(null, 100)).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(isValidNumericInput("", 100)).toBe(false);
  });

  it("returns false for non-numeric string", () => {
    expect(isValidNumericInput("abc", 100)).toBe(false);
  });

  it("returns false for negative number", () => {
    expect(isValidNumericInput("-1", 100)).toBe(false);
  });

  it("returns false for number exceeding max", () => {
    expect(isValidNumericInput("101", 100)).toBe(false);
  });

  it("returns true for valid number within range", () => {
    expect(isValidNumericInput("50", 100)).toBe(true);
  });

  it("returns true for zero", () => {
    expect(isValidNumericInput("0", 100)).toBe(true);
  });

  it("returns true for max value", () => {
    expect(isValidNumericInput("100", 100)).toBe(true);
  });
});

describe("useCommunitySolarPrograms", () => {
  it("is disabled when state is null", () => {
    const { result } = renderHook(() => useCommunitySolarPrograms(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when state is provided", () => {
    mockGetCommunitySolarPrograms.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCommunitySolarPrograms("CT"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useCommunitySolarSavings", () => {
  it("is disabled when bill is null", () => {
    const { result } = renderHook(() => useCommunitySolarSavings(null, "10"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when percent is null", () => {
    const { result } = renderHook(() => useCommunitySolarSavings("200", null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when bill exceeds max", () => {
    const { result } = renderHook(
      () => useCommunitySolarSavings("99999", "10"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled with valid bill and percent", () => {
    mockGetCommunitySolarSavings.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCommunitySolarSavings("200", "15"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useCommunitySolarProgram", () => {
  it("is disabled when programId is null", () => {
    const { result } = renderHook(() => useCommunitySolarProgram(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when programId is provided", () => {
    mockGetCommunitySolarProgram.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCommunitySolarProgram("prog-1"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useCommunitySolarStates", () => {
  it("fetches on mount", () => {
    mockGetCommunitySolarStates.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCommunitySolarStates(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});
