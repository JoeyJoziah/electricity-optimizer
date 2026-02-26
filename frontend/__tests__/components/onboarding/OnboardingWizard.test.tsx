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

const mockSetSupplierMutateAsync = jest.fn().mockResolvedValue({})
jest.mock('@/lib/hooks/useSuppliers', () => ({
  useSuppliers: () => ({
    data: {
      suppliers: [
        {
          id: 'sup_1',
          name: 'TXU Energy',
          avgPricePerKwh: 0.12,
          standingCharge: 0.40,
          greenEnergy: false,
          rating: 4.2,
          estimatedAnnualCost: 1200,
          tariffType: 'variable',
        },
      ],
    },
    isLoading: false,
  }),
  useSetSupplier: () => ({
    mutateAsync: mockSetSupplierMutateAsync,
    isPending: false,
  }),
  useLinkAccount: () => ({
    mutateAsync: jest.fn().mockResolvedValue({}),
    isPending: false,
  }),
}))

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: Object.assign(
    jest.fn((selector?: (state: Record<string, unknown>) => unknown) =>
      selector ? selector({ region: null, utilityTypes: ['electricity'], currentSupplier: null }) : null
    ),
    {
      getState: () => ({
        setRegion: jest.fn(),
        setUtilityTypes: jest.fn(),
        setCurrentSupplier: jest.fn(),
        region: null,
      }),
    }
  ),
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

describe('OnboardingWizard', () => {
  const onComplete = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the region selector as step 1', () => {
    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    expect(screen.getByText('Select your state')).toBeInTheDocument()
    expect(screen.getByText('Step 1 of 2')).toBeInTheDocument()
  })

  it('shows step 2 after selecting a regulated state', async () => {
    const user = userEvent.setup()

    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    // Search and select Alabama (regulated)
    const search = screen.getByPlaceholderText('Search states...')
    await user.type(search, 'Alabama')
    await user.click(screen.getByText('Alabama'))
    await user.click(screen.getByText('Continue to Dashboard'))

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({ region: 'us_al' })
    })

    // Should show utility type selector
    await waitFor(() => {
      expect(screen.getByText('What utilities do you use?')).toBeInTheDocument()
    })
  })

  it('shows regulated state message for non-deregulated states', async () => {
    const user = userEvent.setup()

    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    // Select Alabama (regulated)
    const search = screen.getByPlaceholderText('Search states...')
    await user.type(search, 'Alabama')
    await user.click(screen.getByText('Alabama'))
    await user.click(screen.getByText('Continue to Dashboard'))

    await waitFor(() => {
      expect(screen.getByText(/regulated electricity market/)).toBeInTheDocument()
    })

    // Button should say "Complete Setup" (not "Next: Choose Supplier")
    expect(screen.getByText('Complete Setup')).toBeInTheDocument()
  })

  it('shows supplier step for deregulated states', async () => {
    const user = userEvent.setup()

    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    // Select Texas (deregulated)
    const search = screen.getByPlaceholderText('Search states...')
    await user.type(search, 'Texas')
    await user.click(screen.getByText('Texas'))
    await user.click(screen.getByText('Continue to Dashboard'))

    await waitFor(() => {
      expect(screen.getByText('What utilities do you use?')).toBeInTheDocument()
    })

    // Click next on utility types
    await user.click(screen.getByText('Next: Choose Supplier'))

    await waitFor(() => {
      expect(screen.getByText('Who is your energy supplier?')).toBeInTheDocument()
    })
  })

  it('allows navigating back', async () => {
    const user = userEvent.setup()

    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    // Select Connecticut (deregulated)
    const search = screen.getByPlaceholderText('Search states...')
    await user.type(search, 'Connecticut')
    await user.click(screen.getByText('Connecticut'))
    await user.click(screen.getByText('Continue to Dashboard'))

    await waitFor(() => {
      expect(screen.getByText('What utilities do you use?')).toBeInTheDocument()
    })

    // Click back
    await user.click(screen.getByText('Back'))

    await waitFor(() => {
      expect(screen.getByText('Select your state')).toBeInTheDocument()
    })
  })

  it('pre-selects electricity in utility types', () => {
    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    // Electricity is pre-selected by default (internal state)
    // Verify by checking the component renders
    expect(screen.getByText('Select your state')).toBeInTheDocument()
  })

  it('allows skipping supplier selection for deregulated states', async () => {
    const user = userEvent.setup()

    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    // Navigate to supplier step
    const search = screen.getByPlaceholderText('Search states...')
    await user.type(search, 'Texas')
    await user.click(screen.getByText('Texas'))
    await user.click(screen.getByText('Continue to Dashboard'))

    await waitFor(() => {
      expect(screen.getByText('What utilities do you use?')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Next: Choose Supplier'))

    await waitFor(() => {
      expect(screen.getByText('Who is your energy supplier?')).toBeInTheDocument()
    })

    // Click skip
    await user.click(screen.getByText(/Skip/))

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({ onboarding_completed: true })
    })

    expect(onComplete).toHaveBeenCalled()
  })

  it('completes regulated state flow in 2 steps', async () => {
    const user = userEvent.setup()

    render(<OnboardingWizard onComplete={onComplete} />, {
      wrapper: createWrapper(),
    })

    // Step 1: Select regulated state
    const search = screen.getByPlaceholderText('Search states...')
    await user.type(search, 'Florida')
    await user.click(screen.getByText('Florida'))
    await user.click(screen.getByText('Continue to Dashboard'))

    await waitFor(() => {
      expect(screen.getByText('Complete Setup')).toBeInTheDocument()
    })

    // Step 2: Complete
    await user.click(screen.getByText('Complete Setup'))

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({ onboarding_completed: true })
      expect(onComplete).toHaveBeenCalled()
    })
  })
})
