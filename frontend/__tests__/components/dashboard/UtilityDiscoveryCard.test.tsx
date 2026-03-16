import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { UtilityDiscoveryCard } from '@/components/dashboard/UtilityDiscoveryCard'
import '@testing-library/jest-dom'
import React from 'react'

// Mock settings store
jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      region: 'us_ny',
      utilityTypes: ['electricity'],
    }),
}))

// Mock useUtilityDiscovery
const mockDiscoveryData = {
  state: 'NY',
  count: 4,
  utilities: [
    { utility_type: 'electricity', label: 'Electricity', status: 'deregulated', description: 'Choose your supplier.' },
    { utility_type: 'natural_gas', label: 'Natural Gas', status: 'deregulated', description: 'Compare gas suppliers.' },
    { utility_type: 'heating_oil', label: 'Heating Oil', status: 'available', description: 'Compare heating oil.' },
    { utility_type: 'community_solar', label: 'Community Solar', status: 'available', description: 'Browse solar.' },
  ],
}

jest.mock('@/lib/hooks/useUtilityDiscovery', () => ({
  useUtilityDiscovery: () => ({
    data: mockDiscoveryData,
    isLoading: false,
  }),
}))

// Mock next/link
jest.mock('next/link', () => {
  const MockLink = ({ children, href, ...props }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>{children}</a>
  )
  MockLink.displayName = 'MockLink'
  return MockLink
})

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
  Flame: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-flame" {...props} />,
  Droplets: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-droplets" {...props} />,
  Sun: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-sun" {...props} />,
  ChevronRight: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-chevron" {...props} />,
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-x" {...props} />,
}))

describe('UtilityDiscoveryCard', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('renders header text', () => {
    render(<UtilityDiscoveryCard />, { wrapper })

    expect(screen.getByText('More utilities available in your area')).toBeInTheDocument()
  })

  it('shows untracked utility types', () => {
    render(<UtilityDiscoveryCard />, { wrapper })

    // User tracks electricity, so only other 3 should show
    expect(screen.getByText('Natural Gas')).toBeInTheDocument()
    expect(screen.getByText('Heating Oil')).toBeInTheDocument()
    expect(screen.getByText('Community Solar')).toBeInTheDocument()
    // Electricity should NOT appear (already tracked)
    expect(screen.queryByText('Electricity')).not.toBeInTheDocument()
  })

  it('renders status badges', () => {
    render(<UtilityDiscoveryCard />, { wrapper })

    expect(screen.getByText('Supplier choice')).toBeInTheDocument()
    expect(screen.getAllByText('Available')).toHaveLength(2)
  })

  it('links to correct routes', () => {
    render(<UtilityDiscoveryCard />, { wrapper })

    const gasLink = screen.getByText('Natural Gas').closest('a')
    expect(gasLink).toHaveAttribute('href', '/gas-rates')

    const solarLink = screen.getByText('Community Solar').closest('a')
    expect(solarLink).toHaveAttribute('href', '/community-solar')
  })

  it('renders dismiss button when onDismiss is provided', () => {
    const onDismiss = jest.fn()
    render(<UtilityDiscoveryCard onDismiss={onDismiss} />, { wrapper })

    const dismissBtn = screen.getByLabelText('Dismiss utility suggestions')
    expect(dismissBtn).toBeInTheDocument()

    fireEvent.click(dismissBtn)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('does not render dismiss button when onDismiss is not provided', () => {
    render(<UtilityDiscoveryCard />, { wrapper })

    expect(screen.queryByLabelText('Dismiss utility suggestions')).not.toBeInTheDocument()
  })

  it('renders description text for each utility', () => {
    render(<UtilityDiscoveryCard />, { wrapper })

    expect(screen.getByText('Compare gas suppliers.')).toBeInTheDocument()
    expect(screen.getByText('Compare heating oil.')).toBeInTheDocument()
    expect(screen.getByText('Browse solar.')).toBeInTheDocument()
  })
})

describe('UtilityDiscoveryCard (all tracked)', () => {
  it('returns null when all utilities are tracked', () => {
    // Override mock to track all types
    jest.spyOn(require('@/lib/store/settings'), 'useSettingsStore').mockImplementation(
      (selector: unknown) =>
        typeof selector === 'function'
          ? (selector as (state: Record<string, unknown>) => unknown)({
              region: 'us_ny',
              utilityTypes: ['electricity', 'natural_gas', 'heating_oil', 'community_solar'],
            })
          : undefined
    )

    const queryClient = new QueryClient()
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { container } = render(<UtilityDiscoveryCard />, { wrapper })
    expect(container.firstChild).toBeNull()
  })
})
