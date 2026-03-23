import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

const mockResetPassword = jest.fn();

// useSearchParams must be mocked before dynamic import
let mockToken = "valid-reset-token";

jest.mock("next/navigation", () => ({
  useSearchParams: () => ({
    get: (key: string) => (key === "token" ? mockToken : null),
  }),
}));

jest.mock("@/lib/auth/client", () => ({
  authClient: {
    resetPassword: (...args: unknown[]) => mockResetPassword(...args),
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

import ResetPasswordPage from "@/app/(auth)/auth/reset-password/page";

describe("ResetPasswordPage — with valid token", () => {
  beforeEach(() => {
    mockToken = "valid-reset-token";
    jest.clearAllMocks();
    mockResetPassword.mockResolvedValue(undefined);
  });

  it("renders the set new password heading", () => {
    render(<ResetPasswordPage />);
    expect(
      screen.getByRole("heading", { name: /set new password/i }),
    ).toBeInTheDocument();
  });

  it("renders password and confirm password fields", () => {
    render(<ResetPasswordPage />);
    expect(screen.getByLabelText(/^new password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
  });

  it("renders reset password button", () => {
    render(<ResetPasswordPage />);
    expect(
      screen.getByRole("button", { name: /reset password/i }),
    ).toBeInTheDocument();
  });

  it("shows error when passwords do not match", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/^new password/i), "Password123456");
    await user.type(
      screen.getByLabelText(/confirm password/i),
      "DifferentPass123",
    );
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    expect(mockResetPassword).not.toHaveBeenCalled();
  });

  it("shows error when password is too short (< 12 chars)", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/^new password/i), "Short1");
    await user.type(screen.getByLabelText(/confirm password/i), "Short1");
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    // The error message is the red paragraph — the hint text also contains "12 characters"
    // so query specifically for the error alert paragraph
    expect(
      screen.getByText("Password must be at least 12 characters."),
    ).toBeInTheDocument();
    expect(mockResetPassword).not.toHaveBeenCalled();
  });

  it("calls authClient.resetPassword with password and token", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(
      screen.getByLabelText(/^new password/i),
      "ValidPassword123",
    );
    await user.type(
      screen.getByLabelText(/confirm password/i),
      "ValidPassword123",
    );
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(mockResetPassword).toHaveBeenCalledWith({
        newPassword: "ValidPassword123",
        token: "valid-reset-token",
      });
    });
  });

  it("shows success state after successful reset", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(
      screen.getByLabelText(/^new password/i),
      "ValidPassword123",
    );
    await user.type(
      screen.getByLabelText(/confirm password/i),
      "ValidPassword123",
    );
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password reset successful/i),
      ).toBeInTheDocument();
    });
  });

  it("shows sign in link in success state", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(
      screen.getByLabelText(/^new password/i),
      "ValidPassword123",
    );
    await user.type(
      screen.getByLabelText(/confirm password/i),
      "ValidPassword123",
    );
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      const signInLink = screen.getByRole("link", {
        name: /sign in with your new password/i,
      });
      expect(signInLink).toHaveAttribute("href", "/auth/login");
    });
  });

  it("shows API error message when reset fails", async () => {
    mockResetPassword.mockRejectedValueOnce(new Error("Link has expired"));
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(
      screen.getByLabelText(/^new password/i),
      "ValidPassword123",
    );
    await user.type(
      screen.getByLabelText(/confirm password/i),
      "ValidPassword123",
    );
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText(/link has expired/i)).toBeInTheDocument();
    });
  });
});

describe("ResetPasswordPage — without token", () => {
  beforeEach(() => {
    mockToken = "";
    jest.clearAllMocks();
  });

  it("shows invalid reset link state when no token", () => {
    render(<ResetPasswordPage />);
    expect(screen.getByText(/invalid reset link/i)).toBeInTheDocument();
  });

  it("renders request new link option", () => {
    render(<ResetPasswordPage />);
    const link = screen.getByRole("link", {
      name: /request a new reset link/i,
    });
    expect(link).toHaveAttribute("href", "/auth/forgot-password");
  });
});
