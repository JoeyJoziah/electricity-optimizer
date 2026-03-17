/**
 * Unit tests: Change Password section inside SettingsPage
 *
 * The Settings page renders a "Change Password" <form> that:
 *   - Takes current password, new password, and confirm password inputs
 *   - Validates that new === confirm before calling authClient.changePassword
 *   - Validates minimum length (12 chars) before calling authClient.changePassword
 *   - Shows a success toast on authClient success
 *   - Shows an error toast when authClient returns { error } or throws
 *   - Clears the form fields after a successful password change
 *
 * All heavy store / hook dependencies are mocked identically to settings.test.tsx
 * so this file stays focused purely on the password change behaviour.
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

// ---------------------------------------------------------------------------
// Store mock
// ---------------------------------------------------------------------------

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector?: (s: Record<string, unknown>) => unknown) => {
    const state = {
      region: 'us_ct',
      utilityTypes: ['electricity'],
      currentSupplier: null,
      annualUsageKwh: 10500,
      peakDemandKw: 5.0,
      notificationPreferences: { priceAlerts: true, optimalTimes: true, supplierUpdates: false },
      displayPreferences: { currency: 'USD', theme: 'light', timeFormat: '24h' },
      setRegion: jest.fn(),
      setUtilityTypes: jest.fn(),
      setCurrentSupplier: jest.fn(),
      setAnnualUsage: jest.fn(),
      setPeakDemand: jest.fn(),
      setNotificationPreferences: jest.fn(),
      setDisplayPreferences: jest.fn(),
      resetSettings: jest.fn(),
    }
    return selector ? selector(state as Record<string, unknown>) : state
  },
}))

// ---------------------------------------------------------------------------
// Hook / component mocks (minimal — only what the page actually imports)
// ---------------------------------------------------------------------------

jest.mock('@/lib/hooks/useProfile', () => ({
  useUpdateProfile: () => ({ mutateAsync: jest.fn().mockResolvedValue(undefined), isPending: false }),
}))

jest.mock('@/lib/hooks/useSuppliers', () => ({
  useSuppliers: () => ({ data: { suppliers: [] } }),
  useSetSupplier: () => ({ mutateAsync: jest.fn() }),
  useLinkAccount: () => ({ mutateAsync: jest.fn(), isPending: false }),
  useUserSupplierAccounts: () => ({ data: { accounts: [] } }),
}))

jest.mock('@/lib/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'alice@example.com', name: 'Alice', emailVerified: true },
    isLoading: false,
    isAuthenticated: true,
    error: null,
    signOut: jest.fn(),
  }),
}))

jest.mock('@/components/layout/Header', () => ({
  Header: ({ title }: { title: string }) => <h1>{title}</h1>,
}))

jest.mock('@/components/suppliers/SupplierSelector', () => ({
  SupplierSelector: () => <div data-testid="supplier-selector" />,
}))

jest.mock('@/components/suppliers/SupplierAccountForm', () => ({
  SupplierAccountForm: () => <div data-testid="supplier-account-form" />,
}))

jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
}))

jest.mock('@/lib/constants/regions', () => ({
  US_REGIONS: [
    {
      label: 'Northeast',
      states: [{ value: 'us_ct', label: 'Connecticut', abbr: 'CT' }],
    },
  ],
  DEREGULATED_ELECTRICITY_STATES: new Set(['CT']),
}))

// ---------------------------------------------------------------------------
// Toast mock — capture calls so we can assert on them
// ---------------------------------------------------------------------------

const mockToastSuccess = jest.fn()
const mockToastError = jest.fn()

jest.mock('@/lib/contexts/toast-context', () => ({
  useToast: () => ({
    success: mockToastSuccess,
    error: mockToastError,
  }),
}))

// ---------------------------------------------------------------------------
// authClient mock — the key subject under test
// ---------------------------------------------------------------------------

const mockChangePassword = jest.fn()

jest.mock('@/lib/auth/client', () => ({
  authClient: {
    changePassword: (...args: unknown[]) => mockChangePassword(...args),
    signOut: jest.fn().mockResolvedValue({ data: null, error: null }),
  },
}))

// ---------------------------------------------------------------------------
// Test subject
// ---------------------------------------------------------------------------

import SettingsPage from '@/app/(app)/settings/page'

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/** Fill all three password inputs and submit the form. */
async function fillAndSubmit(
  user: ReturnType<typeof userEvent.setup>,
  {
    current = 'OldPassword123!',
    next = 'NewPassword456!',
    confirm = 'NewPassword456!',
  }: { current?: string; next?: string; confirm?: string } = {}
) {
  await user.type(screen.getByLabelText(/current password/i), current)
  // Use exact label text to avoid matching "Confirm New Password"
  await user.type(screen.getByLabelText('New Password'), next)
  await user.type(screen.getByLabelText('Confirm New Password'), confirm)
  await user.click(screen.getByRole('button', { name: /change password/i }))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Settings page — Change Password section', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Default global.fetch stub for GDPR / other page interactions
    ;(global.fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({}) })
  })

  it('renders the Change Password heading', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('heading', { name: /change password/i })).toBeInTheDocument()
  })

  it('renders current password, new password, and confirm password fields', () => {
    render(<SettingsPage />)
    expect(screen.getByLabelText(/current password/i)).toBeInTheDocument()
    // Use exact label text to distinguish "New Password" from "Confirm New Password"
    expect(screen.getByLabelText('New Password')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm New Password')).toBeInTheDocument()
  })

  it('submit button is disabled when fields are empty', () => {
    render(<SettingsPage />)
    // Button text is "Change Password" — should be disabled with empty inputs
    expect(screen.getByRole('button', { name: /^change password$/i })).toBeDisabled()
  })

  it('calls authClient.changePassword with correct credentials on valid submit', async () => {
    mockChangePassword.mockResolvedValueOnce({ data: {}, error: null })

    const user = userEvent.setup()
    render(<SettingsPage />)

    await fillAndSubmit(user, {
      current: 'OldPassword123!',
      next: 'NewPassword456!',
      confirm: 'NewPassword456!',
    })

    await waitFor(() => {
      expect(mockChangePassword).toHaveBeenCalledWith({
        currentPassword: 'OldPassword123!',
        newPassword: 'NewPassword456!',
      })
    })
  })

  it('shows success toast and clears form fields after a successful password change', async () => {
    mockChangePassword.mockResolvedValueOnce({ data: {}, error: null })

    const user = userEvent.setup()
    render(<SettingsPage />)

    await fillAndSubmit(user)

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith('Password changed', expect.any(String))
    })

    // All three inputs should be cleared
    expect(screen.getByLabelText(/current password/i)).toHaveValue('')
    expect(screen.getByLabelText('New Password')).toHaveValue('')
    expect(screen.getByLabelText('Confirm New Password')).toHaveValue('')
  })

  it('shows error toast when passwords do not match without calling authClient', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)

    await fillAndSubmit(user, {
      current: 'OldPassword123!',
      next: 'NewPassword456!',
      confirm: 'DifferentPassword789!',
    })

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'Passwords do not match',
        expect.any(String)
      )
    })

    expect(mockChangePassword).not.toHaveBeenCalled()
  })

  it('shows error toast when new password is too short without calling authClient', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)

    await fillAndSubmit(user, {
      current: 'OldPassword123!',
      next: 'short',
      confirm: 'short',
    })

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'Password too short',
        expect.any(String)
      )
    })

    expect(mockChangePassword).not.toHaveBeenCalled()
  })

  it('shows error toast when authClient returns an error object', async () => {
    mockChangePassword.mockResolvedValueOnce({
      data: null,
      error: { message: 'Incorrect current password' },
    })

    const user = userEvent.setup()
    render(<SettingsPage />)

    await fillAndSubmit(user)

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'Password change failed',
        'Incorrect current password'
      )
    })
  })

  it('shows fallback error toast when authClient throws unexpectedly', async () => {
    mockChangePassword.mockRejectedValueOnce(new Error('Network error'))

    const user = userEvent.setup()
    render(<SettingsPage />)

    await fillAndSubmit(user)

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'Password change failed',
        expect.stringMatching(/unexpected error/i)
      )
    })
  })
})
