import { render, screen } from '@testing-library/react'
import { DealerList } from '@/components/heating-oil/DealerList'
import '@testing-library/jest-dom'

const mockUseHeatingOilDealers = jest.fn()
jest.mock('@/lib/hooks/useHeatingOil', () => ({
  useHeatingOilDealers: (...args: unknown[]) => mockUseHeatingOilDealers(...args),
}))

const mockDealers = {
  dealers: [
    {
      id: 'd1',
      name: 'New England Fuel Co',
      state: 'CT',
      city: 'Hartford',
      phone: '860-555-0100',
      website: 'https://nefuel.example.com',
      rating: 4.7,
    },
    {
      id: 'd2',
      name: 'Yankee Oil',
      state: 'CT',
      city: 'New Haven',
      phone: null,
      website: null,
      rating: null,
    },
    {
      id: 'd3',
      name: 'Coastal Energy',
      state: 'CT',
      city: null,
      phone: '203-555-0200',
      website: 'https://coastal.example.com',
      rating: 4.2,
    },
  ],
}

describe('DealerList', () => {
  beforeEach(() => {
    mockUseHeatingOilDealers.mockReset()
  })

  it('shows loading skeleton while data is loading', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })
    const { container } = render(<DealerList state="CT" />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('returns null on error', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('fail'),
    })
    const { container } = render(<DealerList state="CT" />)
    expect(container.firstChild).toBeNull()
  })

  it('returns null when no dealers found', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: { dealers: [] },
      isLoading: false,
      error: null,
    })
    const { container } = render(<DealerList state="CT" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders dealer list header with state', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: mockDealers,
      isLoading: false,
      error: null,
    })
    render(<DealerList state="CT" />)
    // Header contains both "Local Dealers" and "CT" via mdash
    expect(screen.getByText(/Local Dealers.*CT/)).toBeInTheDocument()
  })

  it('renders dealer names', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: mockDealers,
      isLoading: false,
      error: null,
    })
    render(<DealerList state="CT" />)
    expect(screen.getByText('New England Fuel Co')).toBeInTheDocument()
    expect(screen.getByText('Yankee Oil')).toBeInTheDocument()
    expect(screen.getByText('Coastal Energy')).toBeInTheDocument()
  })

  it('shows city when available', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: mockDealers,
      isLoading: false,
      error: null,
    })
    render(<DealerList state="CT" />)
    expect(screen.getByText('Hartford, CT')).toBeInTheDocument()
    expect(screen.getByText('New Haven, CT')).toBeInTheDocument()
  })

  it('shows rating badge when available', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: mockDealers,
      isLoading: false,
      error: null,
    })
    render(<DealerList state="CT" />)
    expect(screen.getByText('4.7')).toBeInTheDocument()
    expect(screen.getByText('4.2')).toBeInTheDocument()
  })

  it('renders phone link when available', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: mockDealers,
      isLoading: false,
      error: null,
    })
    render(<DealerList state="CT" />)
    const phoneLink = screen.getByText('860-555-0100')
    expect(phoneLink).toHaveAttribute('href', 'tel:860-555-0100')
  })

  it('renders website link when available', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: mockDealers,
      isLoading: false,
      error: null,
    })
    render(<DealerList state="CT" />)
    const websiteLinks = screen.getAllByText('Website')
    expect(websiteLinks[0]).toHaveAttribute('href', 'https://nefuel.example.com')
    expect(websiteLinks[0]).toHaveAttribute('target', '_blank')
  })

  it('hides phone and website for dealer without them', () => {
    mockUseHeatingOilDealers.mockReturnValue({
      data: { dealers: [mockDealers.dealers[1]] },
      isLoading: false,
      error: null,
    })
    render(<DealerList state="CT" />)
    expect(screen.getByText('Yankee Oil')).toBeInTheDocument()
    expect(screen.queryByText('Website')).not.toBeInTheDocument()
    // No phone links
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
