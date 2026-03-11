import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CompletionProgress } from '@/components/dashboard/CompletionProgress'
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

// Default mock — 1 of 4 tracked
const mockCompletionData = {
  state: 'NY',
  tracked: 1,
  available: 4,
  percent: 25,
  missing: [
    { utility_type: 'natural_gas', label: 'Natural Gas', status: 'deregulated', description: 'Compare gas.' },
    { utility_type: 'heating_oil', label: 'Heating Oil', status: 'available', description: 'Compare oil.' },
    { utility_type: 'community_solar', label: 'Community Solar', status: 'available', description: 'Browse solar.' },
  ],
}

jest.mock('@/lib/hooks/useUtilityDiscovery', () => ({
  useUtilityCompletion: () => ({
    data: mockCompletionData,
  }),
}))

describe('CompletionProgress', () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('renders tracked count', () => {
    render(<CompletionProgress />, { wrapper })

    expect(screen.getByText('1/4')).toBeInTheDocument()
  })

  it('renders label text', () => {
    render(<CompletionProgress />, { wrapper })

    expect(screen.getByText('Utilities tracked')).toBeInTheDocument()
  })

  it('renders missing count text', () => {
    render(<CompletionProgress />, { wrapper })

    expect(screen.getByText('3 more utilities available in your area')).toBeInTheDocument()
  })

  it('renders SVG progress ring', () => {
    render(<CompletionProgress />, { wrapper })

    const circles = document.querySelectorAll('circle')
    expect(circles).toHaveLength(2)
  })

  it('uses singular for 1 missing utility', () => {
    jest.spyOn(require('@/lib/hooks/useUtilityDiscovery'), 'useUtilityCompletion').mockReturnValue({
      data: {
        ...mockCompletionData,
        tracked: 3,
        available: 4,
        percent: 75,
        missing: [{ utility_type: 'community_solar', label: 'Solar', status: 'available', description: 'Solar.' }],
      },
    })

    render(<CompletionProgress />, { wrapper })

    expect(screen.getByText('1 more utility available in your area')).toBeInTheDocument()
  })
})

describe('CompletionProgress (100% complete)', () => {
  it('returns null when all utilities are tracked', () => {
    jest.spyOn(require('@/lib/hooks/useUtilityDiscovery'), 'useUtilityCompletion').mockReturnValue({
      data: {
        state: 'NY',
        tracked: 4,
        available: 4,
        percent: 100,
        missing: [],
      },
    })

    jest.spyOn(require('@/lib/store/settings'), 'useSettingsStore').mockImplementation(
      (selector: (state: Record<string, unknown>) => unknown) =>
        selector({
          region: 'us_ny',
          utilityTypes: ['electricity', 'natural_gas', 'heating_oil', 'community_solar'],
        })
    )

    const queryClient = new QueryClient()
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { container } = render(<CompletionProgress />, { wrapper })
    expect(container.firstChild).toBeNull()
  })
})
