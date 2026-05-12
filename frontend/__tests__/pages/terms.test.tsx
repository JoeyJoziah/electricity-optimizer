import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import TermsPage from "@/app/terms/page";

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

describe("TermsPage", () => {
  beforeEach(() => {
    render(<TermsPage />);
  });

  it("renders the page heading", () => {
    expect(
      screen.getByRole("heading", { level: 1, name: /terms of service/i }),
    ).toBeInTheDocument();
  });

  it("renders last updated date", () => {
    expect(screen.getByText(/last updated/i)).toBeInTheDocument();
  });

  it("renders nav logo linking to home", () => {
    const logoLink = screen.getByRole("link", { name: /rateshift/i });
    expect(logoLink).toHaveAttribute("href", "/");
  });

  it("renders all major section headings", () => {
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /1\. acceptance of terms/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /2\. service description/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /3\. disclaimer/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /4\. subscription and billing/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /5\. user accounts/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /6\. utility data and utilityapi/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /7\. acceptable use/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /8\. api usage/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /9\. limitation of liability/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /10\. changes to terms/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /11\. contact/i }),
    ).toBeInTheDocument();
  });

  it("renders Pro and Business tier references in billing section", () => {
    // Both tiers are named in section 4 ("Pro at $4.99/mo and Business at $14.99/mo")
    expect(screen.getByText(/\$4\.99\/mo/)).toBeInTheDocument();
    expect(screen.getByText(/\$14\.99\/mo/)).toBeInTheDocument();
    expect(screen.getByText(/Stripe/i)).toBeInTheDocument();
  });

  it("renders service description mentioning deregulated electricity markets", () => {
    expect(
      screen.getByText(/deregulated electricity markets/i),
    ).toBeInTheDocument();
  });

  it('does NOT make "all 50 states" geographic claims in service description', () => {
    expect(screen.queryByText(/all 50 states/i)).not.toBeInTheDocument();
  });

  it("renders NREL and EIA data source references", () => {
    expect(screen.getByText(/NREL/)).toBeInTheDocument();
    expect(screen.getByText(/EIA/)).toBeInTheDocument();
  });

  it("renders API usage section for business tier", () => {
    expect(screen.getByText(/API keys are confidential/i)).toBeInTheDocument();
  });

  it("renders legal contact email", () => {
    expect(screen.getByText(/legal@rateshift\.app/i)).toBeInTheDocument();
  });

  it("renders footer navigation links", () => {
    const homeLink = screen.getByRole("link", { name: /^home$/i });
    expect(homeLink).toHaveAttribute("href", "/");

    const pricingLink = screen.getByRole("link", { name: /^pricing$/i });
    expect(pricingLink).toHaveAttribute("href", "/pricing");

    const privacyLink = screen.getByRole("link", { name: /^privacy$/i });
    expect(privacyLink).toHaveAttribute("href", "/privacy");
  });
});
