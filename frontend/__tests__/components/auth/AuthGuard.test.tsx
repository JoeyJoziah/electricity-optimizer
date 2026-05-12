import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseAuth = jest.fn();
const mockRouterReplace = jest.fn();

jest.mock("@/lib/hooks/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockRouterReplace }),
}));

import { AuthGuard } from "@/components/auth/AuthGuard";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AuthGuard", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockRouterReplace.mockReset();
  });

  it("shows loading spinner when isLoading=true", () => {
    mockUseAuth.mockReturnValue({ isLoading: true, isAuthenticated: false });
    const { container } = render(
      <AuthGuard>
        <div data-testid="protected-content">Protected</div>
      </AuthGuard>,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
    // Spinner div should be present
    const spinner = container.querySelector(".animate-spin");
    expect(spinner).toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    mockUseAuth.mockReturnValue({ isLoading: false, isAuthenticated: true });
    render(
      <AuthGuard>
        <div data-testid="protected-content">Protected</div>
      </AuthGuard>,
    );
    expect(screen.getByTestId("protected-content")).toBeInTheDocument();
  });

  it("renders null when not authenticated (redirect in progress)", () => {
    mockUseAuth.mockReturnValue({ isLoading: false, isAuthenticated: false });
    const { container } = render(
      <AuthGuard>
        <div data-testid="protected-content">Protected</div>
      </AuthGuard>,
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  it("calls router.replace with login URL when not authenticated", () => {
    Object.defineProperty(window, "location", {
      value: { pathname: "/dashboard" },
      writable: true,
    });
    mockUseAuth.mockReturnValue({ isLoading: false, isAuthenticated: false });
    render(
      <AuthGuard>
        <div>Protected</div>
      </AuthGuard>,
    );
    expect(mockRouterReplace).toHaveBeenCalledWith(
      expect.stringContaining("/auth/login"),
    );
    expect(mockRouterReplace).toHaveBeenCalledWith(
      expect.stringContaining("callbackUrl"),
    );
  });

  it("does not call router.replace while loading", () => {
    mockUseAuth.mockReturnValue({ isLoading: true, isAuthenticated: false });
    render(
      <AuthGuard>
        <div>Protected</div>
      </AuthGuard>,
    );
    expect(mockRouterReplace).not.toHaveBeenCalled();
  });

  it("does not call router.replace when authenticated", () => {
    mockUseAuth.mockReturnValue({ isLoading: false, isAuthenticated: true });
    render(
      <AuthGuard>
        <div>Protected</div>
      </AuthGuard>,
    );
    expect(mockRouterReplace).not.toHaveBeenCalled();
  });
});
