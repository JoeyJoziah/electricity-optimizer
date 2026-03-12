import { render, screen } from '@testing-library/react'
import { FillUpTiming } from '@/components/propane/FillUpTiming'
import '@testing-library/jest-dom'

const mockUsePropaneTiming = jest.fn()
jest.mock('@/lib/hooks/usePropane', () => ({
  usePropaneTiming: (...args: unknown[]) => mockUsePropaneTiming(...args),
}))

describe('FillUpTiming', () => {
  beforeEach(() => {
    mockUsePropaneTiming.mockReset()
  })

  it('shows loading skeleton', () => {
    mockUsePropaneTiming.mockReturnValue({ data: null, isLoading: true, error: null })
    const { container } = render(<FillUpTiming state="CT" />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders nothing on error', () => {
    mockUsePropaneTiming.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') })
    const { container } = render(<FillUpTiming state="CT" />)
    expect(container.innerHTML).toBe('')
  })

  it('renders good timing advice', () => {
    mockUsePropaneTiming.mockReturnValue({
      data: {
        state: 'CT',
        timing: 'good',
        current_price: 2.5,
        avg_price: 2.8,
        advice: 'Current price is below the 12-month average. Good time to fill up.',
        data_points: 15,
      },
      isLoading: false,
      error: null,
    })
    render(<FillUpTiming state="CT" />)
    expect(screen.getByText('Good Time to Buy')).toBeInTheDocument()
    expect(screen.getByText(/Good time to fill up/)).toBeInTheDocument()
    expect(screen.getByText('$2.50/gal')).toBeInTheDocument()
    expect(screen.getByText('$2.80/gal')).toBeInTheDocument()
  })

  it('renders wait timing advice', () => {
    mockUsePropaneTiming.mockReturnValue({
      data: {
        state: 'CT',
        timing: 'wait',
        current_price: 3.5,
        avg_price: 2.8,
        advice: 'Current price is above the 12-month average. Consider waiting.',
        data_points: 15,
      },
      isLoading: false,
      error: null,
    })
    render(<FillUpTiming state="CT" />)
    expect(screen.getByText('Consider Waiting')).toBeInTheDocument()
    expect(screen.getByText(/Consider waiting/)).toBeInTheDocument()
  })

  it('renders neutral timing advice', () => {
    mockUsePropaneTiming.mockReturnValue({
      data: {
        state: 'CT',
        timing: 'neutral',
        current_price: 2.78,
        avg_price: 2.8,
        advice: 'Price is near the 12-month average.',
        data_points: 15,
      },
      isLoading: false,
      error: null,
    })
    render(<FillUpTiming state="CT" />)
    expect(screen.getByText('Average Pricing')).toBeInTheDocument()
  })
})
