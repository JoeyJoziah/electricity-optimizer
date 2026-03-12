import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AlertPreferences } from '@/components/rate-changes/AlertPreferences'
import '@testing-library/jest-dom'

const mockUseAlertPreferences = jest.fn()
const mockMutate = jest.fn()
const mockUseUpsertAlertPreference = jest.fn()

jest.mock('@/lib/hooks/useRateChanges', () => ({
  useAlertPreferences: () => mockUseAlertPreferences(),
  useUpsertAlertPreference: () => mockUseUpsertAlertPreference(),
}))

const mockPrefs = [
  {
    id: 'pref-1',
    user_id: 'user-1',
    utility_type: 'electricity',
    enabled: true,
    channels: ['email', 'push'],
    cadence: 'daily',
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
  },
  {
    id: 'pref-2',
    user_id: 'user-1',
    utility_type: 'natural_gas',
    enabled: false,
    channels: ['email'],
    cadence: 'weekly',
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
  },
]

describe('AlertPreferences', () => {
  beforeEach(() => {
    mockUseAlertPreferences.mockReset()
    mockUseUpsertAlertPreference.mockReset()
    mockMutate.mockReset()
    mockUseUpsertAlertPreference.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    })
  })

  it('shows loading skeleton', () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: true,
      data: null,
      error: null,
    })
    render(<AlertPreferences />)
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('shows error message', () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: null,
      error: new Error('fail'),
    })
    render(<AlertPreferences />)
    expect(screen.getByText(/Failed to load preferences/)).toBeInTheDocument()
  })

  it('renders all five utility types', () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: { preferences: [] },
      error: null,
    })
    render(<AlertPreferences />)
    expect(screen.getByText('Electricity')).toBeInTheDocument()
    expect(screen.getByText('Natural Gas')).toBeInTheDocument()
    expect(screen.getByText('Heating Oil')).toBeInTheDocument()
    expect(screen.getByText('Propane')).toBeInTheDocument()
    expect(screen.getByText('Community Solar')).toBeInTheDocument()
  })

  it('shows toggle for each utility', () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: { preferences: mockPrefs },
      error: null,
    })
    render(<AlertPreferences />)
    const toggles = screen.getAllByRole('switch')
    expect(toggles).toHaveLength(5)
  })

  it('reflects enabled state from preferences', () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: { preferences: mockPrefs },
      error: null,
    })
    render(<AlertPreferences />)
    const elecToggle = screen.getByLabelText('Toggle Electricity alerts')
    expect(elecToggle).toHaveAttribute('aria-checked', 'true')

    const gasToggle = screen.getByLabelText('Toggle Natural Gas alerts')
    expect(gasToggle).toHaveAttribute('aria-checked', 'false')
  })

  it('calls mutate on toggle click', async () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: { preferences: mockPrefs },
      error: null,
    })
    render(<AlertPreferences />)

    const elecToggle = screen.getByLabelText('Toggle Electricity alerts')
    await userEvent.click(elecToggle)

    expect(mockMutate).toHaveBeenCalledWith({
      utility_type: 'electricity',
      enabled: false,
    })
  })

  it('calls mutate on cadence change', async () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: { preferences: mockPrefs },
      error: null,
    })
    render(<AlertPreferences />)

    const elecCadence = screen.getByLabelText('Electricity cadence')
    await userEvent.selectOptions(elecCadence, 'weekly')

    expect(mockMutate).toHaveBeenCalledWith({
      utility_type: 'electricity',
      cadence: 'weekly',
    })
  })

  it('disables cadence select when utility is disabled', () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: { preferences: mockPrefs },
      error: null,
    })
    render(<AlertPreferences />)

    const gasCadence = screen.getByLabelText('Natural Gas cadence')
    expect(gasCadence).toBeDisabled()
  })

  it('shows saving indicator when mutation is pending', () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: { preferences: mockPrefs },
      error: null,
    })
    mockUseUpsertAlertPreference.mockReturnValue({
      mutate: mockMutate,
      isPending: true,
    })
    render(<AlertPreferences />)
    expect(screen.getByText('Saving...')).toBeInTheDocument()
  })

  it('defaults to enabled when no preference exists', () => {
    mockUseAlertPreferences.mockReturnValue({
      isLoading: false,
      data: { preferences: [] },
      error: null,
    })
    render(<AlertPreferences />)
    const toggles = screen.getAllByRole('switch')
    // All default to enabled (aria-checked=true)
    toggles.forEach((toggle) => {
      expect(toggle).toHaveAttribute('aria-checked', 'true')
    })
  })
})
