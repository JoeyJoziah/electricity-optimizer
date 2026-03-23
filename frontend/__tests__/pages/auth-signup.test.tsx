import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import SignupPage from "@/app/(auth)/auth/signup/page";

// SignupForm has its own comprehensive test suite. Here we test the page wrapper only.
jest.mock("@/components/auth/SignupForm", () => ({
  SignupForm: () => <div data-testid="signup-form">SignupForm</div>,
}));

describe("SignupPage", () => {
  beforeEach(() => {
    render(<SignupPage />);
  });

  it("renders the app name heading", () => {
    expect(
      screen.getByRole("heading", { level: 1, name: /rateshift/i }),
    ).toBeInTheDocument();
  });

  it("renders the create account subtitle", () => {
    expect(
      screen.getByText(/create your account to start saving/i),
    ).toBeInTheDocument();
  });

  it("renders the SignupForm component", () => {
    expect(screen.getByTestId("signup-form")).toBeInTheDocument();
  });

  it("renders within a centered layout container", () => {
    const container = screen
      .getByTestId("signup-form")
      .closest("div.min-h-screen");
    expect(container).not.toBeNull();
  });
});
