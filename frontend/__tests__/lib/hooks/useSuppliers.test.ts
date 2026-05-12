import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetSuppliers = jest.fn();
const mockGetSupplier = jest.fn();
const mockGetRecommendation = jest.fn();
const mockCompareSuppliers = jest.fn();
const mockInitiateSwitch = jest.fn();
const mockGetSwitchStatus = jest.fn();
const mockGetUserSupplier = jest.fn();
const mockSetUserSupplier = jest.fn();
const mockRemoveUserSupplier = jest.fn();
const mockGetUserSupplierAccounts = jest.fn();
const mockLinkSupplierAccount = jest.fn();
const mockUnlinkSupplierAccount = jest.fn();

jest.mock("@/lib/api/suppliers", () => ({
  getSuppliers: (...a: unknown[]) => mockGetSuppliers(...a),
  getSupplier: (...a: unknown[]) => mockGetSupplier(...a),
  getRecommendation: (...a: unknown[]) => mockGetRecommendation(...a),
  compareSuppliers: (...a: unknown[]) => mockCompareSuppliers(...a),
  initiateSwitch: (...a: unknown[]) => mockInitiateSwitch(...a),
  getSwitchStatus: (...a: unknown[]) => mockGetSwitchStatus(...a),
  getUserSupplier: (...a: unknown[]) => mockGetUserSupplier(...a),
  setUserSupplier: (...a: unknown[]) => mockSetUserSupplier(...a),
  removeUserSupplier: (...a: unknown[]) => mockRemoveUserSupplier(...a),
  getUserSupplierAccounts: (...a: unknown[]) =>
    mockGetUserSupplierAccounts(...a),
  linkSupplierAccount: (...a: unknown[]) => mockLinkSupplierAccount(...a),
  unlinkSupplierAccount: (...a: unknown[]) => mockUnlinkSupplierAccount(...a),
}));

import {
  useSuppliers,
  useSupplier,
  useSupplierRecommendation,
  useCompareSuppliers,
  useInitiateSwitch,
  useSwitchStatus,
  useUserSupplier,
  useSetSupplier,
  useRemoveSupplier,
  useUserSupplierAccounts,
  useLinkAccount,
  useUnlinkAccount,
} from "@/lib/hooks/useSuppliers";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useSuppliers", () => {
  it("is disabled when region is null", () => {
    const { result } = renderHook(() => useSuppliers(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when enabled=false", () => {
    const { result } = renderHook(
      () => useSuppliers("us_ct", undefined, false),
      {
        wrapper: makeWrapper(),
      },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when region is provided", () => {
    mockGetSuppliers.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useSuppliers("us_ct"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useSupplier", () => {
  it("is disabled when supplierId is empty string", () => {
    const { result } = renderHook(() => useSupplier(""), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when supplierId is provided", () => {
    mockGetSupplier.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useSupplier("sup-1"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useSupplierRecommendation", () => {
  it("is disabled when annualUsage is 0", () => {
    const { result } = renderHook(
      () => useSupplierRecommendation("sup-1", 0, "us_ct"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when region is null", () => {
    const { result } = renderHook(
      () => useSupplierRecommendation("sup-1", 1000, null),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled when all params are valid", () => {
    mockGetRecommendation.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(
      () => useSupplierRecommendation("sup-1", 1000, "us_ct"),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useCompareSuppliers", () => {
  it("is disabled when supplierIds is empty", () => {
    const { result } = renderHook(() => useCompareSuppliers([], 1000), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when annualUsage is 0", () => {
    const { result } = renderHook(() => useCompareSuppliers(["a", "b"], 0), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is enabled with valid params", () => {
    mockCompareSuppliers.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCompareSuppliers(["a", "b"], 1000), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useSwitchStatus", () => {
  it("is disabled when referenceNumber is empty", () => {
    const { result } = renderHook(() => useSwitchStatus(""), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useInitiateSwitch", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useInitiateSwitch(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });
});

describe("useSetSupplier", () => {
  it("calls setUserSupplier API on mutate", async () => {
    mockSetUserSupplier.mockResolvedValue(undefined);
    const { result } = renderHook(() => useSetSupplier(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate("sup-42");
    });
    expect(mockSetUserSupplier).toHaveBeenCalledWith("sup-42");
  });
});

describe("useRemoveSupplier", () => {
  it("exposes mutate function", () => {
    const { result } = renderHook(() => useRemoveSupplier(), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
  });
});

describe("useUserSupplierAccounts", () => {
  it("fetches on mount", () => {
    mockGetUserSupplierAccounts.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useUserSupplierAccounts(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("fetching");
  });
});

describe("useUnlinkAccount", () => {
  it("calls unlinkSupplierAccount with supplierId", async () => {
    mockUnlinkSupplierAccount.mockResolvedValue(undefined);
    const { result } = renderHook(() => useUnlinkAccount(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate("sup-99");
    });
    expect(mockUnlinkSupplierAccount).toHaveBeenCalledWith("sup-99");
  });
});
