import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import '@testing-library/jest-dom'

// Mock hooks
const mockMutateAsync = jest.fn().mockResolvedValue({})
jest.mock('@/lib/hooks/useProfile', () => ({
  useUpdateProfile: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}))

const mockSetRegion = jest.fn()
const mockSetUtilityTypes = jest.fn()

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: Object.assign(
    jest.fn((selector?: (state: Record<string, unknown>) => unknown) =>
      selector ? selector({ region: null, utilityTypes: ['electricity'], currentSupplier: null }) : null
    ),
    {
      getState: () => ({
        setRegion: mockSetRegion,
        setUtilityTypes: mockSetUtilityTypes,
        region: null,
      }),
    }
  ),
}))

// Mock lucide-react icons used by RegionSelector
jest.mock('lucide-react', () => ({
  MapPin: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Search: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

describe('OnboardingWizard (V2 — Progressive)', () => {
  const onComplete = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the region selector immediately', () => {
    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    expect(screen.getByText('Select your state')).toBeInTheDocument()
  })

  it('does NOT show step indicators (single step)', () => {
    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    expect(screen.queryByText(/Step \d+ of/)).not.toBeInTheDocument()
  })

  it('completes onboarding in one step — select region', async () => {
    const user = userEvent.setup()

    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    // Search and select Alabama
    const search = screen.getByPlaceholderText('Search states...')
    await user.type(search, 'Alabama')
    await user.click(screen.getByText('Alabama'))
    await user.click(screen.getByText('Continue to Dashboard'))

    await waitFor(() => {
      // First call: save region + default utility types
      expect(mockMutateAsync).toHaveBeenCalledWith({
        region: 'us_al',
        utility_types: ['electricity'],
      })
    })

    await waitFor(() => {
      // Second call: mark onboarding complete
      expect(mockMutateAsync).toHaveBeenCalledWith({ onboarding_completed: true })
      expect(onComplete).toHaveBeenCalled()
    })
  })

  it('sets region and utility types in settings store', async () => {
    const user = userEvent.setup()

    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    const search = screen.getByPlaceholderText('Search states...')
    await user.type(search, 'Texas')
    await user.click(screen.getByText('Texas'))
    await user.click(screen.getByText('Continue to Dashboard'))

    await waitFor(() => {
      expect(mockSetRegion).toHaveBeenCalledWith('us_tx')
      expect(mockSetUtilityTypes).toHaveBeenCalledWith(['electricity'])
    })
  })

  it('does NOT show utility type selector (moved to post-signup)', () => {
    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    expect(screen.queryByText('What utilities do you use?')).not.toBeInTheDocument()
  })

  it('does NOT show supplier picker step', () => {
    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    expect(screen.queryByText('Who is your energy supplier?')).not.toBeInTheDocument()
  })

  it('renders state search input', () => {
    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    expect(screen.getByPlaceholderText('Search states...')).toBeInTheDocument()
  })
})
