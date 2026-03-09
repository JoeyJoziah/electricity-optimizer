import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import LandingPage from '@/app/page'

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string; className?: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}))

describe('LandingPage', () => {
  beforeEach(() => {
    render(<LandingPage />)
  })

  it('renders the navigation bar', () => {
    // Appears in nav and footer — use getAllByText
    const matches = screen.getAllByText('Electricity Optimizer')
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })

  it('renders nav links for Pricing and Sign In', () => {
    // Pricing appears in nav and footer — use getAllByRole
    const pricingLinks = screen.getAllByRole('link', { name: /^pricing$/i })
    expect(pricingLinks.length).toBeGreaterThanOrEqual(1)
    expect(pricingLinks[0]).toHaveAttribute('href', '/pricing')

    const signInLink = screen.getByRole('link', { name: /sign in/i })
    expect(signInLink).toHaveAttribute('href', '/auth/login')
  })

  it('renders Get Started nav button linking to signup', () => {
    // Two "Get Started" links: nav + hero CTA
    const getStartedLinks = screen.getAllByRole('link', { name: /get started/i })
    expect(getStartedLinks.length).toBeGreaterThanOrEqual(1)
    expect(getStartedLinks[0]).toHaveAttribute('href', '/auth/signup')
  })

  it('renders the hero heading', () => {
    expect(
      screen.getByRole('heading', { level: 1, name: /save money on your electricity bills/i })
    ).toBeInTheDocument()
  })

  it('renders hero description text', () => {
    expect(screen.getByText(/AI-powered price optimization/i)).toBeInTheDocument()
  })

  it('renders Start Saving Today CTA link', () => {
    const ctaLink = screen.getByRole('link', { name: /start saving today/i })
    expect(ctaLink).toHaveAttribute('href', '/auth/signup')
  })

  it('renders Try It Free link to signup', () => {
    const tryFreeLink = screen.getByRole('link', { name: /try it free/i })
    expect(tryFreeLink).toHaveAttribute('href', '/auth/signup')
  })

  it('renders all 6 feature cards', () => {
    expect(screen.getByText('Real-Time Price Tracking')).toBeInTheDocument()
    expect(screen.getByText('Smart Price Alerts')).toBeInTheDocument()
    expect(screen.getByText('ML-Powered Forecasts')).toBeInTheDocument()
    expect(screen.getByText('Schedule Optimization')).toBeInTheDocument()
    expect(screen.getByText('GDPR Compliant')).toBeInTheDocument()
    expect(screen.getByText('Weather-Aware')).toBeInTheDocument()
  })

  it('renders features section heading', () => {
    expect(
      screen.getByRole('heading', { level: 2, name: /everything you need to optimize energy costs/i })
    ).toBeInTheDocument()
  })

  it('renders pricing section heading', () => {
    expect(
      screen.getByRole('heading', { level: 2, name: /simple, transparent pricing/i })
    ).toBeInTheDocument()
  })

  it('renders all three pricing tiers', () => {
    expect(screen.getByRole('heading', { name: /^free$/i, level: 3 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /^pro$/i, level: 3 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /^business$/i, level: 3 })).toBeInTheDocument()
  })

  it('renders tier pricing', () => {
    expect(screen.getByText('$0')).toBeInTheDocument()
    expect(screen.getByText('$4.99')).toBeInTheDocument()
    expect(screen.getByText('$14.99')).toBeInTheDocument()
  })

  it('renders CTA links for all tiers', () => {
    // "Get Started" appears in nav + Free tier — verify at least one points to signup
    const getStartedLinks = screen.getAllByRole('link', { name: /get started$/i })
    expect(getStartedLinks.length).toBeGreaterThanOrEqual(1)
    expect(getStartedLinks.some(l => l.getAttribute('href') === '/auth/signup')).toBe(true)

    const startTrial = screen.getByRole('link', { name: /start free trial/i })
    expect(startTrial).toHaveAttribute('href', '/auth/signup?plan=pro')

    const contactSales = screen.getByRole('link', { name: /contact sales/i })
    expect(contactSales).toHaveAttribute('href', '/auth/signup?plan=business')
  })

  it('renders footer with copyright text', () => {
    expect(screen.getByText(/electricity optimizer. all rights reserved/i)).toBeInTheDocument()
  })

  it('renders footer links', () => {
    const footerPricing = screen.getAllByRole('link', { name: /^pricing$/i })
    expect(footerPricing.length).toBeGreaterThanOrEqual(1)

    const privacyLinks = screen.getAllByRole('link', { name: /^privacy$/i })
    expect(privacyLinks.length).toBeGreaterThanOrEqual(1)

    const termsLinks = screen.getAllByRole('link', { name: /^terms$/i })
    expect(termsLinks.length).toBeGreaterThanOrEqual(1)
  })
})
