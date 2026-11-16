import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetUserProfile = jest.fn();
const mockUpdateUserProfile = jest.fn();
const mockSetRegion = jest.fn();
const mockGetState = jest.fn(
  (): { region: string | null; setRegion: typeof mockSetRegion } => ({
    region: null,
    setRegion: mockSetRegion,
  }),
);

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
import { waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import "@testing-library/jest-dom";
import type { UserProfile } from "@/lib/api/profile";

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

// ---------------------------------------------------------------------------
// Cases merged from __tests__/hooks/useProfile.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  // --- Helpers ---

  function createWrapper() {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
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

  // --- Mock data ---

  const mockProfile = {
    email: "test@example.com",
    name: "Test User",
    region: "us_ct",
    utility_types: ["electricity"],
    current_supplier_id: "sup-1",
    annual_usage_kwh: 10500,
    onboarding_completed: true,
  };

  const mockProfileNoRegion = {
    email: "newuser@example.com",
    name: null,
    region: null,
    utility_types: null,
    current_supplier_id: null,
    annual_usage_kwh: null,
    onboarding_completed: false,
  };

  // ==========================================================================
  // useProfile
  // ==========================================================================
  describe("useProfile", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockGetUserProfile.mockResolvedValue(mockProfile);
      mockGetState.mockReturnValue({
        region: null,
        setRegion: mockSetRegion,
      });
    });

    it("fetches the user profile successfully", async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useProfile(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockProfile);
      expect(mockGetUserProfile).toHaveBeenCalledTimes(1);
    });

    it("returns loading state before data arrives", () => {
      // Make the profile API hang indefinitely
      mockGetUserProfile.mockReturnValue(new Promise(() => {}));

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useProfile(), { wrapper });

      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toBeUndefined();
    });

    it("syncs region to settings store when profile has a region", async () => {
      const { wrapper } = createWrapper();

      renderHook(() => useProfile(), { wrapper });

      await waitFor(() => {
        expect(mockSetRegion).toHaveBeenCalledWith("us_ct");
      });
    });

    it("does not sync region when profile region is null", async () => {
      mockGetUserProfile.mockResolvedValue(mockProfileNoRegion);

      const { wrapper } = createWrapper();

      renderHook(() => useProfile(), { wrapper });

      await waitFor(() => {
        expect(mockGetUserProfile).toHaveBeenCalled();
      });

      expect(mockSetRegion).not.toHaveBeenCalled();
    });

    it("does not call setRegion when store already has the same region", async () => {
      // Store already has 'us_ct' — profile also returns 'us_ct'
      mockGetState.mockReturnValue({
        region: "us_ct",
        setRegion: mockSetRegion,
      });

      const { wrapper } = createWrapper();

      renderHook(() => useProfile(), { wrapper });

      await waitFor(() => {
        expect(mockGetUserProfile).toHaveBeenCalled();
      });

      // region is the same, no sync needed
      expect(mockSetRegion).not.toHaveBeenCalled();
    });

    it("uses correct query key", async () => {
      const { wrapper, queryClient } = createWrapper();

      renderHook(() => useProfile(), { wrapper });

      await waitFor(() => {
        const keys = queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey);
        expect(keys).toContainEqual(["user-profile"]);
      });
    });

    it("handles API error gracefully", async () => {
      mockGetUserProfile.mockRejectedValue(new Error("Unauthorized"));

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useProfile(), { wrapper });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe("Unauthorized");
      expect(result.current.data).toBeUndefined();
    });

    it("returns profile fields correctly for a new user", async () => {
      mockGetUserProfile.mockResolvedValue(mockProfileNoRegion);

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useProfile(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.email).toBe("newuser@example.com");
      expect(result.current.data?.region).toBeNull();
      expect(result.current.data?.onboarding_completed).toBe(false);
    });
  });

  // ==========================================================================
  // useUpdateProfile
  // ==========================================================================
  describe("useUpdateProfile", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      mockUpdateUserProfile.mockResolvedValue(mockProfile);
      mockGetState.mockReturnValue({
        region: null,
        setRegion: mockSetRegion,
      });
    });

    it("calls updateUserProfile with provided data", async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useUpdateProfile(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          name: "Updated Name",
          region: "us_ct",
        });
      });

      expect(mockUpdateUserProfile).toHaveBeenCalledWith({
        name: "Updated Name",
        region: "us_ct",
      });
    });

    it("returns updated profile data on success", async () => {
      const updatedProfile = { ...mockProfile, name: "Updated Name" };
      mockUpdateUserProfile.mockResolvedValue(updatedProfile);

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useUpdateProfile(), { wrapper });

      let response: UserProfile | undefined;
      await act(async () => {
        response = await result.current.mutateAsync({ name: "Updated Name" });
      });

      expect(response).toEqual(updatedProfile);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });
    });

    it("sets query data in cache after successful update", async () => {
      const { wrapper, queryClient } = createWrapper();

      // Pre-populate the cache so setQueryData has something to update
      queryClient.setQueryData(["user-profile"], mockProfileNoRegion);

      const { result } = renderHook(() => useUpdateProfile(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({ region: "us_ct" });
      });

      // After mutation success, cache should be updated with returned profile
      await waitFor(() => {
        const cached = queryClient.getQueryData(["user-profile"]);
        expect(cached).toEqual(mockProfile);
      });
    });

    it("syncs region to settings store after successful update", async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useUpdateProfile(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({ region: "us_ct" });
      });

      expect(mockSetRegion).toHaveBeenCalledWith("us_ct");
    });

    it("does not sync region when updated profile has no region", async () => {
      mockUpdateUserProfile.mockResolvedValue(mockProfileNoRegion);

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useUpdateProfile(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({ name: "No Region Update" });
      });

      expect(mockSetRegion).not.toHaveBeenCalled();
    });

    it("handles mutation failure and sets error state", async () => {
      mockUpdateUserProfile.mockRejectedValue(new Error("Validation failed"));

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useUpdateProfile(), { wrapper });

      // Use mutate (non-throwing) rather than mutateAsync so we can inspect
      // the error state directly without catching a rejection.
      act(() => {
        result.current.mutate({ name: "Bad Data" });
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
      expect(result.current.error?.message).toBe("Validation failed");
    });

    it("accepts all valid UpdateProfileData fields", async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useUpdateProfile(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          name: "Full Update",
          region: "us_ny",
          utility_types: ["electricity", "natural_gas"],
          current_supplier_id: "sup-99",
          annual_usage_kwh: 12000,
          onboarding_completed: true,
        });
      });

      expect(mockUpdateUserProfile).toHaveBeenCalledWith({
        name: "Full Update",
        region: "us_ny",
        utility_types: ["electricity", "natural_gas"],
        current_supplier_id: "sup-99",
        annual_usage_kwh: 12000,
        onboarding_completed: true,
      });
    });

    it("is in idle state before any mutation is triggered", () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useUpdateProfile(), { wrapper });

      expect(result.current.isPending).toBe(false);
      expect(result.current.isSuccess).toBe(false);
      expect(result.current.isError).toBe(false);
      expect(result.current.data).toBeUndefined();
    });
  });
}
