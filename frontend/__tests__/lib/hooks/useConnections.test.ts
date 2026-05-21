import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockApiClientGet = jest.fn();

jest.mock("@/lib/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockApiClientGet(...args),
  },
  ApiClientError: class ApiClientError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

import { useConnections } from "@/lib/hooks/useConnections";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestWrapper";
  return Wrapper;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useConnections", () => {
  it("fetches on mount", () => {
    mockApiClientGet.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useConnections(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });

  it("returns connections data on success", async () => {
    const connections = [
      {
        id: "c1",
        method: "manual",
        status: "active",
        supplier_name: "EVERSOURCE",
        email_provider: null,
        last_sync_at: null,
        last_sync_error: null,
        current_rate: 0.22,
        created_at: "2025-01-01T00:00:00Z",
      },
    ];
    mockApiClientGet.mockResolvedValue({ connections });
    const { result } = renderHook(() => useConnections(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.connections).toEqual(connections);
  });

  it("remaps connection_type to method", async () => {
    const raw = [
      {
        id: "c2",
        method: "old",
        connection_type: "email",
        status: "active",
        supplier_name: null,
        email_provider: "gmail",
        last_sync_at: null,
        last_sync_error: null,
        current_rate: null,
        created_at: "2025-01-01T00:00:00Z",
      },
    ];
    mockApiClientGet.mockResolvedValue({ connections: raw });
    const { result } = renderHook(() => useConnections(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.connections[0].method).toBe("email");
  });
});
