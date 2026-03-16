import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'

const mockUseProfile = jest.fn()
const mockMutateAsync = jest.fn().mockResolvedValue({})
const mockReplace = jest.fn()

jest.mock('@/lib/hooks/useProfile', () => ({
  useProfile: () => mockUseProfile(),
  useUpdateProfile: () => ({ mutateAsync: mockMutateAsync }),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn(), back: jest.fn() }),
}))

jest.mock('@/components/onboarding/OnboardingWizard', () => ({
  OnboardingWizard: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="onboarding-wizard">
      <button onClick={onComplete}>Complete Onboarding</button>
    </div>
  ),
}))

import OnboardingPage from '@/app/(app)/onboarding/page'

describe('OnboardingPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('shows loading spinner while profile is loading', () => {
    mockUseProfile.mockReturnValue({ data: null, isLoading: true })
    render(<OnboardingPage />)

    const spinner = document.querySelector('.animate-spin')
    expect(spinner).not.toBeNull()
  })

  it('renders OnboardingWizard when profile has no region', () => {
    mockUseProfile.mockReturnValue({
      data: { onboarding_completed: false, region: null },
      isLoading: false,
    })
    render(<OnboardingPage />)

    expect(screen.getByTestId('onboarding-wizard')).toBeInTheDocument()
  })

  it('auto-fixes and redirects when region exists but onboarding_completed is false', async () => {
    mockUseProfile.mockReturnValue({
      data: { onboarding_completed: false, region: 'us_ct' },
      isLoading: false,
    })
    render(<OnboardingPage />)

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({ onboarding_completed: true })
      expect(mockReplace).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('renders null when profile has completed onboarding (redirect pending)', () => {
    mockUseProfile.mockReturnValue({
      data: { onboarding_completed: true, region: 'us_ct' },
      isLoading: false,
    })
    const { container } = render(<OnboardingPage />)

    // Component returns null while redirect fires
    expect(container.firstChild).toBeNull()
  })

  it('redirects to /dashboard when profile is already onboarded', async () => {
    mockUseProfile.mockReturnValue({
      data: { onboarding_completed: true, region: 'us_ct' },
      isLoading: false,
    })
    render(<OnboardingPage />)

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('redirects to /dashboard on wizard completion', async () => {
    mockUseProfile.mockReturnValue({
      data: { onboarding_completed: false, region: null },
      isLoading: false,
    })
    const { getByRole } = render(<OnboardingPage />)

    getByRole('button', { name: /complete onboarding/i }).click()

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('does not show wizard while loading', () => {
    mockUseProfile.mockReturnValue({ data: null, isLoading: true })
    render(<OnboardingPage />)

    expect(screen.queryByTestId('onboarding-wizard')).not.toBeInTheDocument()
  })
})
