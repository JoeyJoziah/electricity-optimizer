import { render } from "@testing-library/react";
import "@testing-library/jest-dom";

const mockRouterReplace = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockRouterReplace,
    push: jest.fn(),
  }),
}));

import AuthCallbackPage from "@/app/(auth)/auth/callback/page";

describe("AuthCallbackPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders a loading spinner", () => {
    render(<AuthCallbackPage />);
    // The spinner uses animate-spin class
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).not.toBeNull();
  });

  it("renders within a full-height centered container", () => {
    render(<AuthCallbackPage />);
    const container = document.querySelector(".min-h-screen");
    expect(container).not.toBeNull();
  });

  it("calls router.replace with /dashboard on mount", () => {
    render(<AuthCallbackPage />);
    expect(mockRouterReplace).toHaveBeenCalledWith("/dashboard");
  });

  it("calls router.replace exactly once", () => {
    render(<AuthCallbackPage />);
    expect(mockRouterReplace).toHaveBeenCalledTimes(1);
  });
});
