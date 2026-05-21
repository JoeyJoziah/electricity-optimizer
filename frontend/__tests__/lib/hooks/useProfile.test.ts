import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetUserProfile = jest.fn();
const mockUpdateUserProfile = jest.fn();
const mockSetRegion = jest.fn();
const mockGetState = jest.fn(() => ({
  region: null,
  setRegion: mockSetRegion,
}));

jest.mock("@/lib/api/profile", () => ({
  getUserProfile: (...args: unknown[]) => mockGetUserProfile(...args),
  updateUserProfile: (...args: unknown[]) => mockUpdateUserProfile(...args),
}));

jest.mock("@/lib/store/settings", () => ({
  useSettingsStore: Object.assign(
    (selector: (state: unknown) => unknown) =>
      selector({ region: null, setRegion: mockSetRegion }),
    { getState: () => mockGetState() },
  ),
}));

import { useProfile, useUpdateProfile } from "@/lib/hooks/useProfile";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestWrapper";
  return Wrapper;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useProfile", () => {
  it("fetches on mount", () => {
    mockGetUserProfile.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useProfile(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useUpdateProfile", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useUpdateProfile(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });

  it("calls updateUserProfile on mutate", async () => {
    mockUpdateUserProfile.mockResolvedValue({ region: "us_ct" });
    const { result } = renderHook(() => useUpdateProfile(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate({ region: "us_ct" });
    });
    expect(mockUpdateUserProfile).toHaveBeenCalledWith({ region: "us_ct" });
  });
});
