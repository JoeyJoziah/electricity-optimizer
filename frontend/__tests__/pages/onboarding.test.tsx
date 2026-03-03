import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'

const mockUseProfile = jest.fn()

jest.mock('@/lib/hooks/useProfile', () => ({
  useProfile: () => mockUseProfile(),
}))

jest.mock('@/components/onboarding/OnboardingWizard', () => ({
  OnboardingWizard: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="onboarding-wizard">
      <button onClick={onComplete}>Complete Onboarding</button>
    </div>
  ),
}))

// Mock window.location.href setter
const mockLocationAssign = jest.fn()
Object.defineProperty(window, 'location', {
  value: { href: '' },
  writable: true,
})

import OnboardingPage from '@/app/(app)/onboarding/page'

describe('OnboardingPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.location.href = ''
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

  it('renders OnboardingWizard when onboarding_completed is false', () => {
    mockUseProfile.mockReturnValue({
      data: { onboarding_completed: false, region: 'us_ct' },
      isLoading: false,
    })
    render(<OnboardingPage />)

    expect(screen.getByTestId('onboarding-wizard')).toBeInTheDocument()
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
      expect(window.location.href).toBe('/dashboard')
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
      expect(window.location.href).toBe('/dashboard')
    })
  })

  it('does not show wizard while loading', () => {
    mockUseProfile.mockReturnValue({ data: null, isLoading: true })
    render(<OnboardingPage />)

    expect(screen.queryByTestId('onboarding-wizard')).not.toBeInTheDocument()
  })
})
