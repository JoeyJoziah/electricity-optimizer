import { renderHook, waitFor } from "@testing-library/react";
import React, { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGetForecast = jest.fn();
const mockGetForecastTypes = jest.fn();

jest.mock("@/lib/api/forecast", () => ({
  getForecast: (...args: unknown[]) => mockGetForecast(...args),
  getForecastTypes: (...args: unknown[]) => mockGetForecastTypes(...args),
}));

import { useForecast, useForecastTypes } from "@/lib/hooks/useForecast";

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

const fakeForecast = { predictions: [], horizon_days: 24 };
const fakeForecastTypes = ["electricity", "gas"];

describe("useForecast", () => {
  beforeEach(() => jest.clearAllMocks());

  it("is disabled when utilityType is undefined", async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useForecast(undefined, "CT", 24), {
      wrapper,
    });
    // fetchStatus should be 'idle' (query not triggered)
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGetForecast).not.toHaveBeenCalled();
  });

  it("is disabled when utilityType is empty string", () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useForecast("", "CT", 24), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGetForecast).not.toHaveBeenCalled();
  });

  it("fires the query when utilityType is provided", async () => {
    mockGetForecast.mockResolvedValue(fakeForecast);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useForecast("electricity", "CT", 24), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetForecast).toHaveBeenCalledWith(
      "electricity",
      "CT",
      24,
      expect.any(AbortSignal),
    );
    expect(result.current.data).toEqual(fakeForecast);
  });

  it("query key includes utilityType, state, and horizonDays", async () => {
    mockGetForecast.mockResolvedValue(fakeForecast);
    const { queryClient, wrapper } = createWrapper();
    renderHook(() => useForecast("electricity", "NY", 48), { wrapper });

    await waitFor(() =>
      expect(
        queryClient.getQueryData(["forecast", "electricity", "NY", 48]),
      ).toBeDefined(),
    );
  });

  it("propagates API errors to the hook result", async () => {
    mockGetForecast.mockRejectedValue(new Error("API error"));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useForecast("electricity", "CT"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe("useForecastTypes", () => {
  beforeEach(() => jest.clearAllMocks());

  it("fetches forecast types on mount", async () => {
    mockGetForecastTypes.mockResolvedValue(fakeForecastTypes);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useForecastTypes(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(fakeForecastTypes);
  });

  it("uses 24-hour staleTime key ['forecast', 'types']", async () => {
    mockGetForecastTypes.mockResolvedValue(fakeForecastTypes);
    const { queryClient, wrapper } = createWrapper();
    renderHook(() => useForecastTypes(), { wrapper });

    await waitFor(() =>
      expect(queryClient.getQueryData(["forecast", "types"])).toBeDefined(),
    );
  });
});
