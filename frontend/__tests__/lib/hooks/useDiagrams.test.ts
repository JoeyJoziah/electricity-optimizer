import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — useDiagrams uses fetch() directly, not an API client module
// ---------------------------------------------------------------------------

const mockFetch = jest.fn();
global.fetch = mockFetch;

import {
  useDiagramList,
  useDiagram,
  useSaveDiagram,
  useCreateDiagram,
} from "@/lib/hooks/useDiagrams";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useDiagramList", () => {
  it("fetches on mount", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDiagramList(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useDiagram", () => {
  it("is disabled when name is null", () => {
    const { result } = renderHook(() => useDiagram(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when name is provided", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDiagram("my-diagram"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useSaveDiagram", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useSaveDiagram(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });
});

describe("useCreateDiagram", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useCreateDiagram(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });
});
