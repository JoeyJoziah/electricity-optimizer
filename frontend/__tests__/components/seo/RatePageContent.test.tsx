import { render, screen } from '@testing-library/react'
import { RatePageContent } from '@/components/seo/RatePageContent'
import '@testing-library/jest-dom'

const mockRateData = {
  state: 'CT',
  utility_type: 'electricity',
  unit: 'kWh',
  average_price: 0.11,
  suppliers: [
    { supplier: 'Eversource', price: 0.12, rate_type: 'standard', updated_at: '2026-03-10' },
    { supplier: 'CheapCo', price: 0.1, rate_type: 'standard', updated_at: '2026-03-10' },
  ],
  count: 2,
}

const breadcrumbs = [
  { name: 'Home', url: 'https://rateshift.app' },
  { name: 'Rates', url: 'https://rateshift.app/rates' },
  { name: 'Connecticut', url: 'https://rateshift.app/rates/connecticut' },
  { name: 'Electricity', url: 'https://rateshift.app/rates/connecticut/electricity' },
]

const defaultProps = {
  stateCode: 'CT',
  stateName: 'Connecticut',
  utilityKey: 'electricity',
  utilityLabel: 'Electricity',
  unit: 'kWh',
  rateData: mockRateData,
  breadcrumbs,
}

describe('RatePageContent', () => {
  it('renders page heading with state and utility', () => {
    render(<RatePageContent {...defaultProps} />)
    expect(screen.getByText('Electricity Rates in Connecticut')).toBeInTheDocument()
  })

  it('renders breadcrumb navigation', () => {
    render(<RatePageContent {...defaultProps} />)
    expect(screen.getByLabelText('Breadcrumb')).toBeInTheDocument()
    expect(screen.getByText('Home')).toBeInTheDocument()
    expect(screen.getByText('Rates')).toBeInTheDocument()
  })

  it('shows average price card', () => {
    render(<RatePageContent {...defaultProps} />)
    expect(screen.getByText('$0.1100')).toBeInTheDocument()
    expect(screen.getByText(/Based on 2 data points/)).toBeInTheDocument()
  })

  it('shows supplier table with prices', () => {
    render(<RatePageContent {...defaultProps} />)
    expect(screen.getByText('Eversource')).toBeInTheDocument()
    expect(screen.getByText('CheapCo')).toBeInTheDocument()
    expect(screen.getByText('$0.1200')).toBeInTheDocument()
    expect(screen.getByText('$0.1000')).toBeInTheDocument()
  })

  it('shows unit in table header', () => {
    render(<RatePageContent {...defaultProps} />)
    expect(screen.getByText(/Rate.*\/kWh/)).toBeInTheDocument()
  })

  it('shows empty state when no rate data', () => {
    render(<RatePageContent {...defaultProps} rateData={null} />)
    expect(
      screen.getByText(/No electricity rate data available for Connecticut/)
    ).toBeInTheDocument()
  })

  it('shows cross-links to other utility types', () => {
    render(<RatePageContent {...defaultProps} />)
    expect(screen.getByText('Natural Gas')).toBeInTheDocument()
    expect(screen.getByText('Heating Oil')).toBeInTheDocument()
  })

  it('does not show current utility in cross-links', () => {
    render(<RatePageContent {...defaultProps} />)
    // Electricity appears in heading but should NOT be a cross-link
    const links = screen
      .getAllByRole('link')
      .filter((l) => l.textContent === 'Electricity')
    // Only breadcrumb link, not a cross-link pill
    expect(links.length).toBeLessThanOrEqual(1)
  })

  it('shows nearby states section', () => {
    render(<RatePageContent {...defaultProps} />)
    expect(screen.getByText(/Electricity Rates in Nearby States/)).toBeInTheDocument()
  })

  it('shows CTA with signup link', () => {
    render(<RatePageContent {...defaultProps} />)
    expect(screen.getByText('Get Started Free')).toBeInTheDocument()
    expect(screen.getByText(/personalized rate alerts/)).toBeInTheDocument()
  })
})
