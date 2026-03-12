import { render, screen } from '@testing-library/react'
import { ConservationTips } from '@/components/water/ConservationTips'
import '@testing-library/jest-dom'

const mockUseWaterTips = jest.fn()
jest.mock('@/lib/hooks/useWater', () => ({
  useWaterTips: () => mockUseWaterTips(),
}))

const MOCK_TIPS = {
  tips: [
    {
      category: 'Indoor',
      title: 'Fix leaky faucets',
      description: 'A faucet dripping wastes 3,000 gallons per year.',
      estimated_savings_gallons: 3000,
      difficulty: 'easy',
    },
    {
      category: 'Outdoor',
      title: 'Water lawns early morning',
      description: 'Reduces evaporation by up to 30%.',
      estimated_savings_gallons: 2000,
      difficulty: 'easy',
    },
    {
      category: 'Monitoring',
      title: 'Check your water meter',
      description: 'Read your meter to detect leaks.',
      estimated_savings_gallons: 0,
      difficulty: 'easy',
    },
  ],
  count: 3,
  estimated_annual_savings_gallons: 5000,
}

describe('ConservationTips', () => {
  beforeEach(() => {
    mockUseWaterTips.mockReset()
  })

  it('shows loading skeleton', () => {
    mockUseWaterTips.mockReturnValue({ data: null, isLoading: true, error: null })
    const { container } = render(<ConservationTips />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders nothing on error', () => {
    mockUseWaterTips.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') })
    const { container } = render(<ConservationTips />)
    expect(container.innerHTML).toBe('')
  })

  it('displays tips grouped by category', () => {
    mockUseWaterTips.mockReturnValue({ data: MOCK_TIPS, isLoading: false, error: null })
    render(<ConservationTips />)

    expect(screen.getByText('Conservation Tips')).toBeInTheDocument()
    expect(screen.getByText('Indoor')).toBeInTheDocument()
    expect(screen.getByText('Outdoor')).toBeInTheDocument()
    expect(screen.getByText('Monitoring')).toBeInTheDocument()
  })

  it('displays tip details', () => {
    mockUseWaterTips.mockReturnValue({ data: MOCK_TIPS, isLoading: false, error: null })
    render(<ConservationTips />)

    expect(screen.getByText('Fix leaky faucets')).toBeInTheDocument()
    expect(screen.getByText('Water lawns early morning')).toBeInTheDocument()
    expect(screen.getByText(/3,000 gallons\/year/)).toBeInTheDocument()
  })

  it('shows total annual savings', () => {
    mockUseWaterTips.mockReturnValue({ data: MOCK_TIPS, isLoading: false, error: null })
    render(<ConservationTips />)

    expect(screen.getByText(/5,000 gal\/year/)).toBeInTheDocument()
  })

  it('shows difficulty badges', () => {
    mockUseWaterTips.mockReturnValue({ data: MOCK_TIPS, isLoading: false, error: null })
    render(<ConservationTips />)

    const easyBadges = screen.getAllByText('easy')
    expect(easyBadges.length).toBe(3)
  })
})
