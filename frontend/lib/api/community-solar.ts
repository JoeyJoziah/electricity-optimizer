/**
 * Community Solar API Client
 *
 * Fetches community solar programs, savings estimates, and state availability.
 */

import { apiClient } from './client'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface CommunitySolarProgram {
  id: string
  state: string
  program_name: string
  provider: string
  savings_percent: string | null
  capacity_kw: string | null
  spots_available: number | null
  enrollment_url: string | null
  enrollment_status: 'open' | 'waitlist' | 'closed'
  description: string | null
  min_bill_amount: string | null
  contract_months: number | null
  updated_at: string | null
}

export interface CommunitySolarProgramsResponse {
  state: string
  count: number
  programs: CommunitySolarProgram[]
}

export interface CommunitySolarSavingsResponse {
  current_monthly_bill: string
  savings_percent: string
  monthly_savings: string
  annual_savings: string
  five_year_savings: string
  new_monthly_bill: string
}

export interface CommunitySolarProgramDetail extends CommunitySolarProgram {
  created_at: string | null
}

export interface CommunitySolarState {
  state: string
  program_count: number
}

export interface CommunitySolarStatesResponse {
  total_states: number
  states: CommunitySolarState[]
}

/* ------------------------------------------------------------------ */
/* API Functions                                                       */
/* ------------------------------------------------------------------ */

export interface GetProgramsParams {
  state: string
  enrollment_status?: 'open' | 'waitlist' | 'closed'
  limit?: number
}

export async function getCommunitySolarPrograms(
  params: GetProgramsParams
): Promise<CommunitySolarProgramsResponse> {
  const query: Record<string, string> = { state: params.state }
  if (params.enrollment_status) query.enrollment_status = params.enrollment_status
  if (params.limit !== undefined) query.limit = String(params.limit)
  return apiClient.get<CommunitySolarProgramsResponse>('/community-solar/programs', query)
}

export interface GetSavingsParams {
  monthly_bill: string
  savings_percent: string
}

export async function getCommunitySolarSavings(
  params: GetSavingsParams
): Promise<CommunitySolarSavingsResponse> {
  return apiClient.get<CommunitySolarSavingsResponse>('/community-solar/savings', {
    monthly_bill: params.monthly_bill,
    savings_percent: params.savings_percent,
  })
}

export async function getCommunitySolarProgram(
  programId: string
): Promise<CommunitySolarProgramDetail> {
  return apiClient.get<CommunitySolarProgramDetail>(`/community-solar/program/${programId}`)
}

export async function getCommunitySolarStates(): Promise<CommunitySolarStatesResponse> {
  return apiClient.get<CommunitySolarStatesResponse>('/community-solar/states')
}
