import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SwitchWizard } from '@/components/suppliers/SwitchWizard'
import '@testing-library/jest-dom'

const mockRecommendation = {
  supplier: {
    id: '2',
    name: 'Bulb Energy',
    logo: '/logos/bulb.png',
    avgPricePerKwh: 0.22,
    standingCharge: 0.45,
    greenEnergy: true,
    rating: 4.3,
    estimatedAnnualCost: 1050,
    tariffType: 'variable' as const,
  },
  currentSupplier: {
    id: '1',
    name: 'British Gas',
    logo: '/logos/bg.png',
    avgPricePerKwh: 0.28,
    standingCharge: 0.55,
    greenEnergy: false,
    rating: 3.8,
    estimatedAnnualCost: 1350,
    tariffType: 'fixed' as const,
    exitFee: 50,
  },
  estimatedSavings: 300,
  paybackMonths: 2,
  confidence: 0.85,
}

describe('SwitchWizard', () => {
  it('shows recommendation in step 1', () => {
    render(<SwitchWizard recommendation={mockRecommendation} />)

    expect(screen.getByText('Bulb Energy')).toBeInTheDocument()
    expect(screen.getByText(/300/)).toBeInTheDocument()
    expect(screen.getByText(/review recommendation/i)).toBeInTheDocument()
  })

  it('displays savings summary on first step', () => {
    render(<SwitchWizard recommendation={mockRecommendation} />)

    expect(screen.getByText(/save/i)).toBeInTheDocument()
    expect(screen.getByText(/year/i)).toBeInTheDocument()
  })

  it('progresses through 4 steps correctly', async () => {
    const user = userEvent.setup()
    render(<SwitchWizard recommendation={mockRecommendation} />)

    // Step 1: Review
    expect(screen.getByText(/review recommendation/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /next/i }))

    // Step 2: GDPR Consent
    await waitFor(() => {
      expect(screen.getByText(/data consent/i)).toBeInTheDocument()
    })

    // Check consent checkbox
    const consentCheckbox = screen.getByRole('checkbox', { name: /consent/i })
    await user.click(consentCheckbox)
    await user.click(screen.getByRole('button', { name: /next/i }))

    // Step 3: Contract Review
    await waitFor(() => {
      expect(screen.getByText(/contract terms/i)).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /next/i }))

    // Step 4: Confirm
    await waitFor(() => {
      expect(screen.getByText(/confirm switch/i)).toBeInTheDocument()
    })
  })

  it('requires GDPR consent before proceeding from step 2', async () => {
    const user = userEvent.setup()
    render(<SwitchWizard recommendation={mockRecommendation} />)

    // Go to step 2
    await user.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      expect(screen.getByText(/data consent/i)).toBeInTheDocument()
    })

    // Try to proceed without consent - button should be disabled
    const nextButton = screen.getByRole('button', { name: /next/i })
    expect(nextButton).toBeDisabled()

    // Enable after checking consent
    const consentCheckbox = screen.getByRole('checkbox', { name: /consent/i })
    await user.click(consentCheckbox)
    expect(nextButton).not.toBeDisabled()
  })

  it('shows exit fees and contract details in step 3', async () => {
    const user = userEvent.setup()
    render(<SwitchWizard recommendation={mockRecommendation} />)

    // Navigate to step 3
    await user.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      const consentCheckbox = screen.getByRole('checkbox', { name: /consent/i })
      user.click(consentCheckbox)
    })

    await user.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      expect(screen.getByText(/exit fee/i)).toBeInTheDocument()
      expect(screen.getByText(/50/)).toBeInTheDocument()
    })
  })

  it('calls onComplete when switch is confirmed', async () => {
    const onComplete = jest.fn()
    const user = userEvent.setup()

    render(<SwitchWizard recommendation={mockRecommendation} onComplete={onComplete} />)

    // Step 1: Review
    await user.click(screen.getByRole('button', { name: /next/i }))

    // Step 2: Consent
    await waitFor(async () => {
      const consentCheckbox = screen.getByRole('checkbox', { name: /consent/i })
      await user.click(consentCheckbox)
    })
    await user.click(screen.getByRole('button', { name: /next/i }))

    // Step 3: Contract
    await waitFor(() => {
      expect(screen.getByText(/contract terms/i)).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /next/i }))

    // Step 4: Confirm
    await waitFor(() => {
      expect(screen.getByText(/confirm switch/i)).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalled()
    })
  })

  it('allows going back to previous steps', async () => {
    const user = userEvent.setup()
    render(<SwitchWizard recommendation={mockRecommendation} />)

    // Go forward to step 2
    await user.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      expect(screen.getByText(/data consent/i)).toBeInTheDocument()
    })

    // Go back to step 1
    await user.click(screen.getByRole('button', { name: /back/i }))

    await waitFor(() => {
      expect(screen.getByText(/review recommendation/i)).toBeInTheDocument()
    })
  })

  it('calls onCancel when cancel button is clicked', async () => {
    const onCancel = jest.fn()
    const user = userEvent.setup()

    render(<SwitchWizard recommendation={mockRecommendation} onCancel={onCancel} />)

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onCancel).toHaveBeenCalled()
  })

  it('shows step progress indicator', () => {
    render(<SwitchWizard recommendation={mockRecommendation} />)

    expect(screen.getByText(/step 1 of 4/i)).toBeInTheDocument()
  })

  it('displays confidence level for the recommendation', () => {
    render(<SwitchWizard recommendation={mockRecommendation} />)

    expect(screen.getByText(/85%/)).toBeInTheDocument()
  })

  it('shows comparison between current and new supplier', () => {
    render(<SwitchWizard recommendation={mockRecommendation} />)

    expect(screen.getByText('British Gas')).toBeInTheDocument()
    expect(screen.getByText('Bulb Energy')).toBeInTheDocument()
  })

  it('handles API errors gracefully', async () => {
    const onComplete = jest.fn().mockRejectedValue(new Error('API Error'))
    const user = userEvent.setup()

    render(<SwitchWizard recommendation={mockRecommendation} onComplete={onComplete} />)

    // Navigate through all steps
    await user.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(async () => {
      await user.click(screen.getByRole('checkbox', { name: /consent/i }))
    })
    await user.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => {
      expect(screen.getByText(/contract terms/i)).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => {
      expect(screen.getByText(/confirm switch/i)).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument()
    })
  })

  it('shows loading state during submission', async () => {
    const onComplete = jest.fn(
      () => new Promise((resolve) => setTimeout(resolve, 1000))
    )
    const user = userEvent.setup()

    render(<SwitchWizard recommendation={mockRecommendation} onComplete={onComplete} />)

    // Navigate through all steps quickly
    await user.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(async () => {
      await user.click(screen.getByRole('checkbox', { name: /consent/i }))
    })
    await user.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => {
      expect(screen.getByText(/contract terms/i)).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => {
      expect(screen.getByText(/confirm switch/i)).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    // Should show loading state
    expect(screen.getByText(/processing/i)).toBeInTheDocument()
  })

  it('is accessible with proper ARIA labels', () => {
    render(<SwitchWizard recommendation={mockRecommendation} />)

    // Wizard should be a dialog or region
    expect(screen.getByRole('region', { name: /supplier switching wizard/i })).toBeInTheDocument()
  })
})
