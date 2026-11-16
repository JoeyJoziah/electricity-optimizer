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
import { ReactNode } from "react";
import "@testing-library/jest-dom";

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
    expect(result.current.data?.connections[0]?.method).toBe("email");
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/hooks/useConnections.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  const mockGet = mockApiClientGet;

  function createWrapper() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    return {
      queryClient,
      wrapper: ({ children }: { children: ReactNode }) =>
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          children,
        ),
    };
  }

  const mockConnectionsResponse = {
    connections: [
      {
        id: "conn-1",
        method: "direct",
        connection_type: "direct",
        status: "active",
        supplier_name: "Eversource",
        email_provider: null,
        last_sync_at: "2026-03-10T10:00:00Z",
        last_sync_error: null,
        current_rate: 0.18,
        created_at: "2026-03-01T10:00:00Z",
        label: null,
      },
    ],
  };

  describe("useConnections", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGet.mockResolvedValue(mockConnectionsResponse);
    });

    it("fetches connections", async () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useConnections(), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.connections).toHaveLength(1);
      expect(result.current.data?.connections[0]!.supplier_name).toBe(
        "Eversource",
      );
    });

    it("maps connection_type to method", async () => {
      mockGet.mockResolvedValue({
        connections: [
          {
            id: "conn-2",
            method: "old_method",
            connection_type: "email_import",
            status: "active",
            supplier_name: null,
            email_provider: "gmail",
            last_sync_at: null,
            last_sync_error: null,
            current_rate: null,
            created_at: "2026-03-01T10:00:00Z",
          },
        ],
      });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useConnections(), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      // connection_type should override method
      expect(result.current.data?.connections[0]!.method).toBe("email_import");
    });

    it("uses correct query key", async () => {
      const { wrapper, queryClient } = createWrapper();
      renderHook(() => useConnections(), { wrapper });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual(["connections"]);
      });
    });

    it("handles 403 error with upgrade message", async () => {
      const { ApiClientError } = jest.requireMock("@/lib/api/client");
      mockGet.mockRejectedValue(new ApiClientError("Forbidden", 403));

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useConnections(), { wrapper });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error?.message).toBe("upgrade");
    });

    it("handles generic network error", async () => {
      mockGet.mockRejectedValue(new Error("Network error"));

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useConnections(), { wrapper });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error?.message).toBe("Network error");
    });
  });
}
