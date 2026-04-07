import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import PricingPage from "@/app/pricing/page";

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

describe("PricingPage", () => {
  beforeEach(() => {
    render(<PricingPage />);
  });

  it("renders the page heading", () => {
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /simple, transparent pricing/i,
      }),
    ).toBeInTheDocument();
  });

  it("renders nav logo link back to home", () => {
    const logoLink = screen.getByRole("link", { name: /rateshift/i });
    expect(logoLink).toHaveAttribute("href", "/");
  });

  it("renders Sign In link in nav", () => {
    const signInLink = screen.getByRole("link", { name: /sign in/i });
    expect(signInLink).toHaveAttribute("href", "/auth/login");
  });

  it("renders Get Started nav link", () => {
    const getStartedLink = screen.getByRole("link", { name: /^get started$/i });
    expect(getStartedLink).toHaveAttribute("href", "/auth/signup");
  });

  it("renders all three tier headings", () => {
    expect(
      screen.getByRole("heading", { level: 2, name: /^free$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /^pro$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /^business$/i }),
    ).toBeInTheDocument();
  });

  it("renders correct pricing amounts", () => {
    expect(screen.getByText("$0")).toBeInTheDocument();
    expect(screen.getByText("$4.99")).toBeInTheDocument();
    expect(screen.getByText("$14.99")).toBeInTheDocument();
  });

  it("renders Most Popular badge on Pro tier", () => {
    expect(screen.getByText("Most Popular")).toBeInTheDocument();
  });

  it("renders free tier features", () => {
    expect(
      screen.getByText("Real-time electricity prices"),
    ).toBeInTheDocument();
    expect(screen.getByText("1 price alert")).toBeInTheDocument();
    expect(screen.getByText("Basic dashboard")).toBeInTheDocument();
  });

  it("renders pro tier features", () => {
    expect(screen.getByText("ML-powered 24hr forecasts")).toBeInTheDocument();
    expect(screen.getByText("Smart schedule optimization")).toBeInTheDocument();
    expect(
      screen.getByText("Savings tracker & gamification"),
    ).toBeInTheDocument();
  });

  it("renders business tier features", () => {
    expect(screen.getByText("REST API access")).toBeInTheDocument();
    expect(screen.getByText("Multi-property management")).toBeInTheDocument();
    expect(screen.getByText("Priority email support")).toBeInTheDocument();
    expect(screen.getByText("White-glove onboarding")).toBeInTheDocument();
  });

  it('does NOT render "Dedicated account manager" claim', () => {
    expect(
      screen.queryByText("Dedicated account manager"),
    ).not.toBeInTheDocument();
  });

  it('does NOT make "all 50 states" coverage claims in pricing copy', () => {
    expect(screen.queryByText(/all 50 states/i)).not.toBeInTheDocument();
  });

  it("renders CTA links with correct hrefs", () => {
    const getStartedFree = screen.getByRole("link", {
      name: /get started free/i,
    });
    expect(getStartedFree).toHaveAttribute("href", "/auth/signup");

    const startTrial = screen.getByRole("link", { name: /start free trial/i });
    expect(startTrial).toHaveAttribute("href", "/auth/signup?plan=pro");

    const contactSales = screen.getByRole("link", { name: /contact sales/i });
    expect(contactSales).toHaveAttribute("href", "/auth/signup?plan=business");
  });

  it("renders FAQ section heading", () => {
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /frequently asked questions/i,
      }),
    ).toBeInTheDocument();
  });

  it("renders FAQ questions", () => {
    expect(screen.getByText(/can I cancel anytime\?/i)).toBeInTheDocument();
    expect(screen.getByText(/what payment methods/i)).toBeInTheDocument();
    expect(screen.getByText(/is my data secure\?/i)).toBeInTheDocument();
    expect(
      screen.getByText(/where does the price data come from\?/i),
    ).toBeInTheDocument();
  });

  it("renders Privacy Policy link in FAQ", () => {
    const privacyLink = screen.getByRole("link", { name: /privacy policy/i });
    expect(privacyLink).toHaveAttribute("href", "/privacy");
  });

  it("renders footer links", () => {
    const homeLink = screen.getByRole("link", { name: /^home$/i });
    expect(homeLink).toHaveAttribute("href", "/");
  });
});
