import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

const mockRequestPasswordReset = jest.fn();

jest.mock("@/lib/auth/client", () => ({
  authClient: {
    requestPasswordReset: (...args: unknown[]) =>
      mockRequestPasswordReset(...args),
  },
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import ForgotPasswordPage from "@/app/(auth)/auth/forgot-password/page";

describe("ForgotPasswordPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequestPasswordReset.mockResolvedValue(undefined);
  });

  it("renders the reset password heading", () => {
    render(<ForgotPasswordPage />);
    expect(
      screen.getByRole("heading", { name: /reset your password/i }),
    ).toBeInTheDocument();
  });

  it("renders the email input", () => {
    render(<ForgotPasswordPage />);
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it("renders the send reset link button", () => {
    render(<ForgotPasswordPage />);
    expect(
      screen.getByRole("button", { name: /send reset link/i }),
    ).toBeInTheDocument();
  });

  it("renders back to sign in link", () => {
    render(<ForgotPasswordPage />);
    const backLink = screen.getAllByRole("link", { name: /back to sign in/i });
    expect(backLink.length).toBeGreaterThanOrEqual(1);
    expect(backLink[0]).toHaveAttribute("href", "/auth/login");
  });

  it("calls authClient.requestPasswordReset with email on submit", async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(
      screen.getByLabelText(/email address/i),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(mockRequestPasswordReset).toHaveBeenCalledWith({
        email: "user@example.com",
        redirectTo: "/auth/reset-password",
      });
    });
  });

  it("shows success state after submission", async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(
      screen.getByLabelText(/email address/i),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/check your email/i)).toBeInTheDocument();
    });
  });

  it("shows submitted email in success state", async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(
      screen.getByLabelText(/email address/i),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/user@example\.com/)).toBeInTheDocument();
    });
  });

  it("shows back to sign in link in success state", async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(
      screen.getByLabelText(/email address/i),
      "test@example.com",
    );
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      const backLink = screen.getByRole("link", { name: /back to sign in/i });
      expect(backLink).toHaveAttribute("href", "/auth/login");
    });
  });

  it("shows error message when requestPasswordReset throws", async () => {
    mockRequestPasswordReset.mockRejectedValueOnce(new Error("Network error"));
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(
      screen.getByLabelText(/email address/i),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/network error/i)).toBeInTheDocument();
    });
  });

  it("shows sending state while submitting", async () => {
    mockRequestPasswordReset.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(
      screen.getByLabelText(/email address/i),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(
      screen.getByRole("button", { name: /sending/i }),
    ).toBeInTheDocument();
  });

  it("disables submit button while loading", async () => {
    mockRequestPasswordReset.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(
      screen.getByLabelText(/email address/i),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled();
  });
});
