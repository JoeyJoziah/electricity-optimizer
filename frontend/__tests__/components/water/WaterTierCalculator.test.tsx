import { render, screen, fireEvent } from '@testing-library/react'
import { WaterTierCalculator } from '@/components/water/WaterTierCalculator'
import '@testing-library/jest-dom'

const mockUseWaterRates = jest.fn()
jest.mock('@/lib/hooks/useWater', () => ({
  useWaterRates: (...args: unknown[]) => mockUseWaterRates(...args),
}))

const MOCK_RATES = {
  rates: [
    {
      id: 'uuid-1',
      municipality: 'New York',
      state: 'NY',
      rate_tiers: [
        { limit_gallons: 3000, rate_per_gallon: 0.004 },
        { limit_gallons: 6000, rate_per_gallon: 0.006 },
        { limit_gallons: null, rate_per_gallon: 0.009 },
      ],
      base_charge: 15.50,
      unit: 'gallon',
      effective_date: '2026-01-01',
      source_url: null,
      updated_at: null,
    },
    {
      id: 'uuid-2',
      municipality: 'Buffalo',
      state: 'NY',
      rate_tiers: [
        { limit_gallons: 4000, rate_per_gallon: 0.005 },
        { limit_gallons: null, rate_per_gallon: 0.008 },
      ],
      base_charge: 12.00,
      unit: 'gallon',
      effective_date: null,
      source_url: null,
      updated_at: null,
    },
  ],
  count: 2,
}

describe('WaterTierCalculator', () => {
  beforeEach(() => {
    mockUseWaterRates.mockReset()
  })

  it('shows loading skeleton', () => {
    mockUseWaterRates.mockReturnValue({ data: null, isLoading: true, error: null })
    const { container } = render(<WaterTierCalculator state="NY" />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders nothing on error', () => {
    mockUseWaterRates.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') })
    const { container } = render(<WaterTierCalculator state="NY" />)
    expect(container.innerHTML).toBe('')
  })

  it('renders municipality selector', () => {
    mockUseWaterRates.mockReturnValue({ data: MOCK_RATES, isLoading: false, error: null })
    render(<WaterTierCalculator state="NY" />)

    expect(screen.getByText('Water Cost Calculator')).toBeInTheDocument()
    expect(screen.getByLabelText('Municipality')).toBeInTheDocument()
    expect(screen.getByLabelText('Monthly Usage (gallons)')).toBeInTheDocument()
  })

  it('shows cost breakdown when municipality selected', () => {
    mockUseWaterRates.mockReturnValue({ data: MOCK_RATES, isLoading: false, error: null })
    render(<WaterTierCalculator state="NY" />)

    fireEvent.change(screen.getByLabelText('Municipality'), { target: { value: 'New York' } })

    expect(screen.getByText('Estimated Monthly Bill')).toBeInTheDocument()
    expect(screen.getByText('Base charge')).toBeInTheDocument()
    // Default usage is 5760 gallons
    // Tier 1: 3000 * 0.004 = 12.00
    // Tier 2: 2760 * 0.006 = 16.56
    // Total tier charges: 28.56, base: 15.50, total: 44.06
    expect(screen.getByText(/44\.06/)).toBeInTheDocument()
  })

  it('does not show breakdown when no municipality selected', () => {
    mockUseWaterRates.mockReturnValue({ data: MOCK_RATES, isLoading: false, error: null })
    render(<WaterTierCalculator state="NY" />)

    expect(screen.queryByText('Estimated Monthly Bill')).not.toBeInTheDocument()
  })
})
