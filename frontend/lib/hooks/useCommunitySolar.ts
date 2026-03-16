/**
 * React Query hooks for community solar data.
 */

import { useQuery } from '@tanstack/react-query'
import {
  getCommunitySolarPrograms,
  getCommunitySolarSavings,
  getCommunitySolarProgram,
  getCommunitySolarStates,
} from '@/lib/api/community-solar'

// ---------------------------------------------------------------------------
// Numeric validation helpers (exported for testing)
// ---------------------------------------------------------------------------

/** Max monthly bill: $50,000 (commercial accounts) */
export const MAX_MONTHLY_BILL = 50_000

/** Max savings percent: 100% */
export const MAX_SAVINGS_PERCENT = 100

/**
 * Validate that a numeric string is a non-negative number within a max bound.
 * Returns true if the value parses to a finite number in [0, maxValue].
 */
export function isValidNumericInput(value: string | null, maxValue: number): boolean {
  if (!value) return false
  const num = Number(value)
  return Number.isFinite(num) && num >= 0 && num <= maxValue
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useCommunitySolarPrograms(
  state: string | null | undefined,
  enrollmentStatus?: 'open' | 'waitlist' | 'closed'
) {
  return useQuery({
    queryKey: ['community-solar', 'programs', state, enrollmentStatus],
    queryFn: ({ signal }) =>
      getCommunitySolarPrograms({
        state: state!,
        enrollment_status: enrollmentStatus,
      }, signal),
    enabled: !!state,
    staleTime: 600_000, // 10 min — programs don't change often
  })
}

export function useCommunitySolarSavings(
  monthlyBill: string | null,
  savingsPercent: string | null
) {
  const validBill = isValidNumericInput(monthlyBill, MAX_MONTHLY_BILL)
  const validPercent = isValidNumericInput(savingsPercent, MAX_SAVINGS_PERCENT)

  return useQuery({
    queryKey: ['community-solar', 'savings', monthlyBill, savingsPercent],
    queryFn: ({ signal }) =>
      getCommunitySolarSavings({
        monthly_bill: monthlyBill!,
        savings_percent: savingsPercent!,
      }, signal),
    enabled: validBill && validPercent,
    staleTime: 300_000,
  })
}

export function useCommunitySolarProgram(programId: string | null) {
  return useQuery({
    queryKey: ['community-solar', 'program', programId],
    queryFn: ({ signal }) => getCommunitySolarProgram(programId!, signal),
    enabled: !!programId,
    staleTime: 600_000,
  })
}

export function useCommunitySolarStates() {
  return useQuery({
    queryKey: ['community-solar', 'states'],
    queryFn: ({ signal }) => getCommunitySolarStates(signal),
    staleTime: 3_600_000, // 1 hour
  })
}
