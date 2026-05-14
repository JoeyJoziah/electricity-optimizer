import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { QueryProvider } from "@/components/providers/QueryProvider";

// Test that QueryProvider correctly wraps children with a React Query context
// by rendering a component that uses useQuery inside the provider.
function TestConsumer() {
  const { status } = useQuery({
    queryKey: ["test"],
    queryFn: () => Promise.resolve("data"),
    enabled: false,
  });
  return <div data-testid="query-consumer">status: {status}</div>;
}

describe("QueryProvider", () => {
  it("renders children without crashing", () => {
    render(
      <QueryProvider>
        <p data-testid="child">Hello</p>
      </QueryProvider>,
    );

    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("provides a React Query context to children", () => {
    // If QueryProvider does not wrap a QueryClientProvider, useQuery throws.
    // This test passing proves the context is provided.
    expect(() => {
      render(
        <QueryProvider>
          <TestConsumer />
        </QueryProvider>,
      );
    }).not.toThrow();

    expect(screen.getByTestId("query-consumer")).toBeInTheDocument();
  });

  it("useQuery has pending status when query is disabled", () => {
    render(
      <QueryProvider>
        <TestConsumer />
      </QueryProvider>,
    );

    // With enabled: false, status should be 'pending'
    expect(screen.getByText(/status: pending/i)).toBeInTheDocument();
  });

  it("renders multiple children", () => {
    render(
      <QueryProvider>
        <p data-testid="first">First</p>
        <p data-testid="second">Second</p>
      </QueryProvider>,
    );

    expect(screen.getByTestId("first")).toBeInTheDocument();
    expect(screen.getByTestId("second")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// retry / retryDelay branch coverage via QueryClient introspection
// ---------------------------------------------------------------------------

describe("QueryProvider retry function", () => {
  function getRetry() {
    const { result } = renderHook(() => useQueryClient(), {
      wrapper: QueryProvider,
    });
    const retry = result.current.getDefaultOptions().queries?.retry;
    if (typeof retry !== "function") throw new Error("retry is not a function");
    return retry as (failureCount: number, error: unknown) => boolean;
  }

  it("returns false for 4xx client errors", () => {
    const retry = getRetry();
    expect(retry(1, { status: 400 })).toBe(false);
    expect(retry(1, { status: 404 })).toBe(false);
    expect(retry(1, { status: 422 })).toBe(false);
    expect(retry(1, { status: 499 })).toBe(false);
  });

  it("returns true for 503 on first attempt, false after", () => {
    const retry = getRetry();
    expect(retry(0, { status: 503 })).toBe(true);
    expect(retry(1, { status: 503 })).toBe(false);
  });

  it("retries up to 2 times for other 5xx errors", () => {
    const retry = getRetry();
    expect(retry(0, { status: 500 })).toBe(true);
    expect(retry(1, { status: 500 })).toBe(true);
    expect(retry(2, { status: 500 })).toBe(false);
  });

  it("retries non-http errors up to 2 times", () => {
    const retry = getRetry();
    expect(retry(0, new TypeError("network failure"))).toBe(true);
    expect(retry(1, new TypeError("network failure"))).toBe(true);
    expect(retry(2, new TypeError("network failure"))).toBe(false);
  });

  it("returns false when error has no status property", () => {
    const retry = getRetry();
    // Error objects without status default to 0, which is < 400, so retries allowed
    expect(retry(2, {})).toBe(false);
    expect(retry(0, {})).toBe(true);
  });

  it("returns false when error has non-numeric status", () => {
    const retry = getRetry();
    // status that isn't a number defaults to 0
    expect(retry(0, { status: "bad" })).toBe(true); // 0 < 400, retries allowed
    expect(retry(2, { status: "bad" })).toBe(false);
  });
});

describe("QueryProvider retryDelay function", () => {
  function getRetryDelay() {
    const { result } = renderHook(() => useQueryClient(), {
      wrapper: QueryProvider,
    });
    const retryDelay = result.current.getDefaultOptions().queries?.retryDelay;
    if (typeof retryDelay !== "function")
      throw new Error("retryDelay is not a function");
    return retryDelay as (attemptIndex: number, error: unknown) => number;
  }

  it("returns 3000 for 503 errors", () => {
    const retryDelay = getRetryDelay();
    expect(retryDelay(0, { status: 503 })).toBe(3000);
    expect(retryDelay(1, { status: 503 })).toBe(3000);
  });

  it("uses exponential backoff for non-503 errors", () => {
    const retryDelay = getRetryDelay();
    expect(retryDelay(0, { status: 500 })).toBe(1000); // 1000 * 2^0
    expect(retryDelay(1, { status: 500 })).toBe(2000); // 1000 * 2^1
    expect(retryDelay(2, { status: 500 })).toBe(4000); // 1000 * 2^2
  });

  it("caps exponential backoff at 30000ms", () => {
    const retryDelay = getRetryDelay();
    expect(retryDelay(10, { status: 500 })).toBe(30000);
  });

  it("uses exponential backoff for errors with no status", () => {
    const retryDelay = getRetryDelay();
    expect(retryDelay(0, {})).toBe(1000);
    expect(retryDelay(0, null)).toBe(1000);
  });
});
