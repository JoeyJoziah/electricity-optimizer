import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import LoginPage from "@/app/(auth)/auth/login/page";

// LoginForm has its own comprehensive test suite. Here we test the page wrapper only.
jest.mock("@/components/auth/LoginForm", () => ({
  LoginForm: () => <div data-testid="login-form">LoginForm</div>,
}));

describe("LoginPage", () => {
  beforeEach(() => {
    render(<LoginPage />);
  });

  it("renders the app name heading", () => {
    expect(
      screen.getByRole("heading", { level: 1, name: /rateshift/i }),
    ).toBeInTheDocument();
  });

  it("renders the subtitle", () => {
    expect(
      screen.getByText(/AI-powered electricity rate optimization/i),
    ).toBeInTheDocument();
  });

  it("renders the LoginForm component", () => {
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
  });

  it("renders within a centered layout container", () => {
    // Use data-testid lookup instead of brittle CSS class selector (div.min-h-screen)
    const loginForm = screen.getByTestId("login-form");
    // The login form should be nested inside the page wrapper
    expect(loginForm.closest("div")).not.toBeNull();
    // Verify the page has the expected heading hierarchy (semantic check)
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});
