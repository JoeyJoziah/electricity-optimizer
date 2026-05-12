import { renderHook, act } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockApiPost = jest.fn();

jest.mock("@/lib/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockApiPost(...args),
  },
}));

import { useGeocoding } from "@/lib/hooks/useGeocoding";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useGeocoding", () => {
  beforeEach(() => {
    mockApiPost.mockReset();
  });

  it("starts with loading=false and no error", () => {
    const { result } = renderHook(() => useGeocoding());
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(typeof result.current.geocode).toBe("function");
  });

  it("sets loading=true while request is in flight", async () => {
    let resolve!: (value: unknown) => void;
    mockApiPost.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );

    const { result } = renderHook(() => useGeocoding());
    act(() => {
      result.current.geocode("123 Main St");
    });
    expect(result.current.loading).toBe(true);
    resolve({
      result: {
        lat: 41.7,
        lng: -72.7,
        state: "CT",
        formatted_address: "123 Main St, CT",
      },
    });
  });

  it("returns geocode result and resets loading on success", async () => {
    const geoResult = {
      lat: 41.7,
      lng: -72.7,
      state: "CT",
      formatted_address: "123 Main St",
    };
    mockApiPost.mockResolvedValue({ result: geoResult });

    const { result } = renderHook(() => useGeocoding());
    let returned: unknown;
    await act(async () => {
      returned = await result.current.geocode("123 Main St");
    });
    expect(returned).toEqual(geoResult);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("returns null and sets error when API fails", async () => {
    mockApiPost.mockRejectedValue(new Error("Network failure"));

    const { result } = renderHook(() => useGeocoding());
    let returned: unknown;
    await act(async () => {
      returned = await result.current.geocode("bad address");
    });
    expect(returned).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe("Network failure");
  });

  it("returns null when API response has null result", async () => {
    mockApiPost.mockResolvedValue({ result: null });

    const { result } = renderHook(() => useGeocoding());
    let returned: unknown;
    await act(async () => {
      returned = await result.current.geocode("unknown address");
    });
    expect(returned).toBeNull();
  });

  it("geocode function is stable across re-renders", () => {
    const { result, rerender } = renderHook(() => useGeocoding());
    const first = result.current.geocode;
    rerender();
    expect(result.current.geocode).toBe(first);
  });
});
