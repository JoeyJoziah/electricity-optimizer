import { render, screen } from '@testing-library/react'
import { RateChangeCard } from '@/components/rate-changes/RateChangeCard'
import '@testing-library/jest-dom'
import type { RateChange } from '@/lib/api/rate-changes'

const mockIncrease: RateChange = {
  id: 'rc-1',
  utility_type: 'electricity',
  region: 'us_ct',
  supplier: 'Eversource',
  previous_price: 0.1,
  current_price: 0.12,
  change_pct: 20.0,
  change_direction: 'increase',
  detected_at: '2026-03-10T06:30:00Z',
  recommendation_supplier: 'CheapCo',
  recommendation_price: 0.08,
  recommendation_savings: 0.04,
}

const mockDecrease: RateChange = {
  id: 'rc-2',
  utility_type: 'natural_gas',
  region: 'TX',
  supplier: 'TXU',
  previous_price: 1.0,
  current_price: 0.8,
  change_pct: -20.0,
  change_direction: 'decrease',
  detected_at: '2026-03-09T06:30:00Z',
  recommendation_supplier: null,
  recommendation_price: null,
  recommendation_savings: null,
}

describe('RateChangeCard', () => {
  it('renders utility type label', () => {
    render(<RateChangeCard change={mockIncrease} />)
    expect(screen.getByText('Electricity')).toBeInTheDocument()
  })

  it('renders region and supplier', () => {
    render(<RateChangeCard change={mockIncrease} />)
    expect(screen.getByText(/us_ct/)).toBeInTheDocument()
    expect(screen.getByText(/Eversource/)).toBeInTheDocument()
  })

  it('shows increase badge with danger styling', () => {
    render(<RateChangeCard change={mockIncrease} />)
    const badge = screen.getByText(/20\.0%/)
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain('text-danger-700')
  })

  it('shows decrease badge with success styling', () => {
    render(<RateChangeCard change={mockDecrease} />)
    const badge = screen.getByText(/20\.0%/)
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain('text-success-700')
  })

  it('renders previous and current prices', () => {
    render(<RateChangeCard change={mockIncrease} />)
    expect(screen.getByText(/\$0\.1000/)).toBeInTheDocument()
    expect(screen.getByText(/\$0\.1200/)).toBeInTheDocument()
  })

  it('shows unit label for utility type', () => {
    render(<RateChangeCard change={mockIncrease} />)
    expect(screen.getAllByText(/\/kWh/).length).toBeGreaterThanOrEqual(1)
  })

  it('shows gas unit label', () => {
    render(<RateChangeCard change={mockDecrease} />)
    expect(screen.getAllByText(/\/therm/).length).toBeGreaterThanOrEqual(1)
  })

  it('shows recommendation when available', () => {
    render(<RateChangeCard change={mockIncrease} />)
    expect(screen.getByText(/Switch to CheapCo/)).toBeInTheDocument()
    expect(screen.getByText(/\$0\.0800/)).toBeInTheDocument()
    expect(screen.getByText(/save \$0\.0400/)).toBeInTheDocument()
  })

  it('hides recommendation when not available', () => {
    render(<RateChangeCard change={mockDecrease} />)
    expect(screen.queryByText(/Switch to/)).not.toBeInTheDocument()
  })

  it('shows detected date', () => {
    render(<RateChangeCard change={mockIncrease} />)
    expect(screen.getByText(/Detected/)).toBeInTheDocument()
  })
})
