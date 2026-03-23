import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

const mockVerifyEmail = jest.fn();
const mockSendVerificationEmail = jest.fn();

let mockToken: string | null = null;
let mockEmail: string | null = null;

jest.mock("next/navigation", () => ({
  useSearchParams: () => ({
    get: (key: string) => {
      if (key === "token") return mockToken;
      if (key === "email") return mockEmail;
      return null;
    },
  }),
}));

jest.mock("@/lib/auth/client", () => ({
  authClient: {
    verifyEmail: (...args: unknown[]) => mockVerifyEmail(...args),
    sendVerificationEmail: (...args: unknown[]) =>
      mockSendVerificationEmail(...args),
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

import VerifyEmailPage from "@/app/(auth)/auth/verify-email/page";

describe("VerifyEmailPage — no token (check email screen)", () => {
  beforeEach(() => {
    mockToken = null;
    mockEmail = null;
    jest.clearAllMocks();
    mockSendVerificationEmail.mockResolvedValue({ data: {} });
  });

  it("renders check your email heading", () => {
    render(<VerifyEmailPage />);
    expect(
      screen.getByRole("heading", { name: /check your email/i }),
    ).toBeInTheDocument();
  });

  it("renders resend verification email button", () => {
    render(<VerifyEmailPage />);
    expect(
      screen.getByRole("button", { name: /resend verification email/i }),
    ).toBeInTheDocument();
  });

  it("renders back to sign in link", () => {
    render(<VerifyEmailPage />);
    const link = screen.getByRole("link", { name: /back to sign in/i });
    expect(link).toHaveAttribute("href", "/auth/login");
  });

  it("shows email address in the message when email param provided", () => {
    mockEmail = "user@example.com";
    render(<VerifyEmailPage />);
    expect(screen.getByText(/user@example\.com/)).toBeInTheDocument();
  });

  it("shows email input field when no email param", () => {
    render(<VerifyEmailPage />);
    const emailInput = screen.getByPlaceholderText(
      /enter your email to resend/i,
    );
    expect(emailInput).toBeInTheDocument();
  });

  it("calls sendVerificationEmail with email on resend", async () => {
    mockEmail = "user@example.com";
    const user = userEvent.setup();
    render(<VerifyEmailPage />);

    await user.click(
      screen.getByRole("button", { name: /resend verification email/i }),
    );

    await waitFor(() => {
      expect(mockSendVerificationEmail).toHaveBeenCalledWith({
        email: "user@example.com",
      });
    });
  });

  it("shows confirmation after successful resend", async () => {
    mockEmail = "user@example.com";
    const user = userEvent.setup();
    render(<VerifyEmailPage />);

    await user.click(
      screen.getByRole("button", { name: /resend verification email/i }),
    );

    await waitFor(() => {
      expect(screen.getByText(/verification email sent/i)).toBeInTheDocument();
    });
  });

  it("disables resend button when email is empty", () => {
    render(<VerifyEmailPage />);
    const button = screen.getByRole("button", {
      name: /resend verification email/i,
    });
    expect(button).toBeDisabled();
  });

  it("shows error message when sendVerificationEmail returns error", async () => {
    mockEmail = "user@example.com";
    mockSendVerificationEmail.mockResolvedValue({
      error: { message: "User not found" },
    });
    const user = userEvent.setup();
    render(<VerifyEmailPage />);

    await user.click(
      screen.getByRole("button", { name: /resend verification email/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(/unable to send verification email/i),
      ).toBeInTheDocument();
    });
  });

  it("shows error message when sendVerificationEmail throws", async () => {
    mockEmail = "user@example.com";
    mockSendVerificationEmail.mockRejectedValue(new Error("Network error"));
    const user = userEvent.setup();
    render(<VerifyEmailPage />);

    await user.click(
      screen.getByRole("button", { name: /resend verification email/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(/unable to send verification email/i),
      ).toBeInTheDocument();
    });
  });
});

describe("VerifyEmailPage — with valid token", () => {
  beforeEach(() => {
    mockToken = "valid-token-123";
    mockEmail = null;
    jest.clearAllMocks();
  });

  it("shows verifying state initially", () => {
    mockVerifyEmail.mockReturnValue(new Promise(() => {}));
    render(<VerifyEmailPage />);
    expect(screen.getByText(/verifying your email/i)).toBeInTheDocument();
  });

  it("calls authClient.verifyEmail with the token", async () => {
    mockVerifyEmail.mockResolvedValue({ data: {} });
    render(<VerifyEmailPage />);

    await waitFor(() => {
      expect(mockVerifyEmail).toHaveBeenCalledWith({
        query: { token: "valid-token-123" },
      });
    });
  });

  it("shows email verified success state after verification", async () => {
    mockVerifyEmail.mockResolvedValue({ data: {} });
    render(<VerifyEmailPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /email verified/i }),
      ).toBeInTheDocument();
    });
  });

  it("shows go to sign in link after verification", async () => {
    mockVerifyEmail.mockResolvedValue({ data: {} });
    render(<VerifyEmailPage />);

    await waitFor(() => {
      const link = screen.getByRole("link", { name: /go to sign in/i });
      expect(link).toHaveAttribute("href", "/auth/login");
    });
  });
});

describe("VerifyEmailPage — with invalid token", () => {
  beforeEach(() => {
    mockToken = "expired-token";
    mockEmail = null;
    jest.clearAllMocks();
  });

  it("shows verification failed state when token is invalid", async () => {
    mockVerifyEmail.mockRejectedValue(new Error("Token expired"));
    render(<VerifyEmailPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /verification failed/i }),
      ).toBeInTheDocument();
    });
  });

  it("shows error message from the thrown error", async () => {
    mockVerifyEmail.mockRejectedValue(new Error("Token expired"));
    render(<VerifyEmailPage />);

    await waitFor(() => {
      expect(screen.getByText(/token expired/i)).toBeInTheDocument();
    });
  });

  it("shows request new verification email link", async () => {
    mockVerifyEmail.mockRejectedValue(new Error("Token expired"));
    render(<VerifyEmailPage />);

    await waitFor(() => {
      const link = screen.getByRole("link", {
        name: /request a new verification email/i,
      });
      expect(link).toHaveAttribute("href", "/auth/verify-email");
    });
  });

  it("shows error when verifyEmail returns error object", async () => {
    mockVerifyEmail.mockResolvedValue({ error: { message: "Token expired" } });
    render(<VerifyEmailPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /verification failed/i }),
      ).toBeInTheDocument();
      expect(screen.getByText(/token expired/i)).toBeInTheDocument();
    });
  });

  it("only calls verifyEmail once even in StrictMode double-render", async () => {
    mockVerifyEmail.mockResolvedValue({ data: {} });
    render(<VerifyEmailPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /email verified/i }),
      ).toBeInTheDocument();
    });

    expect(mockVerifyEmail).toHaveBeenCalledTimes(1);
  });
});
