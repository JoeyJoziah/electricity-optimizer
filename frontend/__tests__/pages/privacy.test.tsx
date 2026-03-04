import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import PrivacyPage from '@/app/privacy/page'

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string; className?: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}))

describe('PrivacyPage', () => {
  beforeEach(() => {
    render(<PrivacyPage />)
  })

  it('renders the page heading', () => {
    expect(
      screen.getByRole('heading', { level: 1, name: /privacy policy/i })
    ).toBeInTheDocument()
  })

  it('renders last updated date', () => {
    expect(screen.getByText(/last updated/i)).toBeInTheDocument()
  })

  it('renders nav logo linking to home', () => {
    const logoLink = screen.getByRole('link', { name: /electricity optimizer/i })
    expect(logoLink).toHaveAttribute('href', '/')
  })

  it('renders all major section headings', () => {
    expect(screen.getByRole('heading', { level: 2, name: /1\. information we collect/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /2\. how we use/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /3\. data storage/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /4\. gdpr compliance/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /5\. third-party services/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /6\. cookies/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /7\. data retention/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /8\. contact/i })).toBeInTheDocument()
  })

  it('renders GDPR compliance content', () => {
    // Appears in both section heading and body text — use getAllBy
    const gdprItems = screen.getAllByText(/GDPR compliance/i)
    expect(gdprItems.length).toBeGreaterThanOrEqual(1)
  })

  it('renders data retention period', () => {
    expect(screen.getByText(/730 days/i)).toBeInTheDocument()
  })

  it('renders third-party services mentioned', () => {
    expect(screen.getByText(/NREL/)).toBeInTheDocument()
    expect(screen.getByText(/Stripe/)).toBeInTheDocument()
    expect(screen.getByText(/Resend/)).toBeInTheDocument()
  })

  it('renders privacy contact email', () => {
    expect(screen.getByText(/privacy@electricity-optimizer\.com/i)).toBeInTheDocument()
  })

  it('renders footer navigation links', () => {
    const homeLink = screen.getByRole('link', { name: /^home$/i })
    expect(homeLink).toHaveAttribute('href', '/')

    const pricingLink = screen.getByRole('link', { name: /^pricing$/i })
    expect(pricingLink).toHaveAttribute('href', '/pricing')

    const termsLink = screen.getByRole('link', { name: /^terms$/i })
    expect(termsLink).toHaveAttribute('href', '/terms')
  })
})
