import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import UnsubscribedPage from "@/app/unsubscribed/page";

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

describe("UnsubscribedPage", () => {
  beforeEach(() => {
    render(<UnsubscribedPage />);
  });

  it("renders the unsubscribed confirmation heading", () => {
    expect(
      screen.getByRole("heading", { name: /unsubscribed/i }),
    ).toBeInTheDocument();
  });

  it("confirms emails will no longer be sent", () => {
    expect(
      screen.getByText(/no longer receive onboarding emails/i),
    ).toBeInTheDocument();
  });

  it("reassures user that account remains active", () => {
    expect(screen.getByText(/account remains active/i)).toBeInTheDocument();
  });

  it("renders nav logo linking to home", () => {
    const logoLink = screen.getAllByRole("link", { name: /rateshift/i })[0];
    expect(logoLink).toHaveAttribute("href", "/");
  });

  it("renders a return-to-home link", () => {
    const returnLink = screen.getByRole("link", {
      name: /return to rateshift/i,
    });
    expect(returnLink).toHaveAttribute("href", "/");
  });
});
