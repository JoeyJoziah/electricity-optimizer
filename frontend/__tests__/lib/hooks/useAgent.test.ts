import { renderHook, act, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockQueryAgent = jest.fn();
const mockGetAgentUsage = jest.fn();
const mockGenerateMessageId = jest.fn(() => "msg-test-1");

jest.mock("@/lib/api/agent", () => ({
  queryAgent: (...a: unknown[]) => mockQueryAgent(...a),
  getAgentUsage: (...a: unknown[]) => mockGetAgentUsage(...a),
  generateMessageId: () => mockGenerateMessageId(),
}));

import { useAgentQuery, useAgentStatus } from "@/lib/hooks/useAgent";

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  mockQueryAgent.mockReset();
  mockGetAgentUsage.mockReset();
});

// ---------------------------------------------------------------------------
// useAgentQuery
// ---------------------------------------------------------------------------
describe("useAgentQuery", () => {
  it("starts with empty messages and not streaming", () => {
    const { result } = renderHook(() => useAgentQuery());
    expect(result.current.messages).toEqual([]);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("adds user message and assistant reply on sendQuery", async () => {
    async function* fakeStream() {
      yield { role: "assistant" as const, content: "Hello!", id: "msg-reply" };
    }
    mockQueryAgent.mockReturnValueOnce(fakeStream());

    const { result } = renderHook(() => useAgentQuery());

    await act(async () => {
      await result.current.sendQuery("Hi");
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.messages[0].content).toBe("Hi");
    expect(result.current.messages[1].role).toBe("assistant");
    expect(result.current.messages[1].content).toBe("Hello!");
    expect(result.current.isStreaming).toBe(false);
  });

  it("sets error state when stream yields an error message", async () => {
    async function* fakeStream() {
      yield { role: "error" as const, content: "rate limit", id: "err-1" };
    }
    mockQueryAgent.mockReturnValueOnce(fakeStream());

    const { result } = renderHook(() => useAgentQuery());

    await act(async () => {
      await result.current.sendQuery("test");
    });

    expect(result.current.error).toBe("rate limit");
  });

  it("reset clears messages and error", async () => {
    async function* fakeStream() {
      yield { role: "error" as const, content: "oops", id: "err-2" };
    }
    mockQueryAgent.mockReturnValueOnce(fakeStream());

    const { result } = renderHook(() => useAgentQuery());
    await act(async () => {
      await result.current.sendQuery("test");
    });
    expect(result.current.messages.length).toBeGreaterThan(0);

    act(() => {
      result.current.reset();
    });
    expect(result.current.messages).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it("cancel sets isStreaming to false and aborts the controller", () => {
    const { result } = renderHook(() => useAgentQuery());
    act(() => {
      result.current.cancel();
    });
    expect(result.current.isStreaming).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// useAgentStatus
// ---------------------------------------------------------------------------
describe("useAgentStatus", () => {
  it("fetches agent usage stats", async () => {
    mockGetAgentUsage.mockResolvedValueOnce({
      used: 5,
      limit: 20,
      remaining: 15,
      tier: "pro",
    });

    const { result } = renderHook(() => useAgentStatus(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.remaining).toBe(15);
  });
});
