import { renderHook, act } from "@testing-library/react";

const mockPost = jest.fn();

jest.mock("@/lib/api/client", () => ({
  apiClient: { post: (...args: unknown[]) => mockPost(...args) },
}));

import { useGeocoding } from "@/lib/hooks/useGeocoding";

const fakeResult = {
  lat: 41.76,
  lng: -72.67,
  state: "CT",
  formatted_address: "Hartford, CT",
};

describe("useGeocoding", () => {
  beforeEach(() => jest.clearAllMocks());

  it("starts with loading=false and error=null", () => {
    const { result } = renderHook(() => useGeocoding());
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("sets loading=true during the request and false after", async () => {
    let resolve!: (v: unknown) => void;
    mockPost.mockReturnValue(new Promise((r) => (resolve = r)));
    const { result } = renderHook(() => useGeocoding());

    let geocodePromise!: Promise<unknown>;
    act(() => {
      geocodePromise = result.current.geocode("Hartford, CT");
    });

    expect(result.current.loading).toBe(true);

    await act(async () => {
      resolve({ result: fakeResult });
      await geocodePromise;
    });

    expect(result.current.loading).toBe(false);
  });

  it("returns the geocode result on success", async () => {
    mockPost.mockResolvedValue({ result: fakeResult });
    const { result } = renderHook(() => useGeocoding());

    let geocodeResult: unknown;
    await act(async () => {
      geocodeResult = await result.current.geocode("Hartford, CT");
    });

    expect(geocodeResult).toEqual(fakeResult);
    expect(result.current.error).toBeNull();
  });

  it("returns null when response.result is null", async () => {
    mockPost.mockResolvedValue({ result: null });
    const { result } = renderHook(() => useGeocoding());

    let geocodeResult: unknown;
    await act(async () => {
      geocodeResult = await result.current.geocode("Unknown Place");
    });

    expect(geocodeResult).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("sets error state on API failure", async () => {
    mockPost.mockRejectedValue(new Error("Network error"));
    const { result } = renderHook(() => useGeocoding());

    await act(async () => {
      await result.current.geocode("Bad address");
    });

    expect(result.current.error).toBe("Network error");
    expect(result.current.loading).toBe(false);
  });

  it("sets generic error message when error is not an Error instance", async () => {
    mockPost.mockRejectedValue("some string error");
    const { result } = renderHook(() => useGeocoding());

    await act(async () => {
      await result.current.geocode("Bad address");
    });

    expect(result.current.error).toBe("Geocoding failed");
  });

  it("cancels the previous request when a new one is issued", async () => {
    let firstResolve!: (v: unknown) => void;
    const firstAbortSignals: AbortSignal[] = [];

    mockPost.mockImplementation(
      (_url: string, _body: unknown, opts: { signal?: AbortSignal }) => {
        if (opts?.signal) firstAbortSignals.push(opts.signal);
        return new Promise((r) => (firstResolve = r));
      },
    );

    const { result } = renderHook(() => useGeocoding());

    act(() => {
      result.current.geocode("Address 1");
    });

    // Issue second request before the first resolves
    mockPost.mockResolvedValue({ result: fakeResult });
    await act(async () => {
      await result.current.geocode("Address 2");
    });

    // The AbortSignal for the first request should be aborted
    expect(firstAbortSignals[0]?.aborted).toBe(true);
  });

  it("discards a stale response when a newer request completes first", async () => {
    // First call is slow; second call resolves immediately
    let firstResolve!: (v: unknown) => void;
    const firstPromise = new Promise((r) => (firstResolve = r));
    mockPost
      .mockReturnValueOnce(firstPromise)
      .mockResolvedValueOnce({ result: { ...fakeResult, state: "NY" } });

    const { result } = renderHook(() => useGeocoding());

    let firstResult: unknown;
    let secondResult: unknown;

    act(() => {
      result.current.geocode("Address 1").then((r) => (firstResult = r));
    });

    await act(async () => {
      secondResult = await result.current.geocode("Address 2");
    });

    // Now resolve the slow first request — its result should be discarded
    await act(async () => {
      firstResolve({ result: fakeResult });
      await firstPromise;
    });

    expect(secondResult).toEqual({ ...fakeResult, state: "NY" });
    // First request returns null because it is stale
    expect(firstResult).toBeNull();
  });

  it("silently returns null on AbortError without setting error state", async () => {
    const abortError = new DOMException("Aborted", "AbortError");
    mockPost.mockRejectedValue(abortError);
    const { result } = renderHook(() => useGeocoding());

    let geocodeResult: unknown;
    await act(async () => {
      geocodeResult = await result.current.geocode("Some address");
    });

    expect(geocodeResult).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
