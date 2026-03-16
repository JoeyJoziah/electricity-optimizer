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

export function useCommunitySolarPrograms(
  state: string | null | undefined,
  enrollmentStatus?: 'open' | 'waitlist' | 'closed'
) {
  return useQuery({
    queryKey: ['community-solar', 'programs', state, enrollmentStatus],
    queryFn: () =>
      getCommunitySolarPrograms({
        state: state!,
        enrollment_status: enrollmentStatus,
      }),
    enabled: !!state,
    staleTime: 600_000, // 10 min — programs don't change often
  })
}

export function useCommunitySolarSavings(
  monthlyBill: string | null,
  savingsPercent: string | null
) {
  return useQuery({
    queryKey: ['community-solar', 'savings', monthlyBill, savingsPercent],
    queryFn: () =>
      getCommunitySolarSavings({
        monthly_bill: monthlyBill!,
        savings_percent: savingsPercent!,
      }),
    enabled: !!monthlyBill && !!savingsPercent,
    staleTime: 300_000,
  })
}

export function useCommunitySolarProgram(programId: string | null) {
  return useQuery({
    queryKey: ['community-solar', 'program', programId],
    queryFn: () => getCommunitySolarProgram(programId!),
    enabled: !!programId,
    staleTime: 600_000,
  })
}

export function useCommunitySolarStates() {
  return useQuery({
    queryKey: ['community-solar', 'states'],
    queryFn: getCommunitySolarStates,
    staleTime: 3_600_000, // 1 hour
  })
}
