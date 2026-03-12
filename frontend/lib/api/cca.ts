import { apiClient } from './client'

export interface CCAProgram {
  id: string
  state: string
  municipality: string
  program_name: string
  provider: string
  generation_mix: Record<string, number> | null
  rate_vs_default_pct: number | null
  opt_out_url: string | null
  program_url: string | null
  status: string
}

export interface CCADetectResponse {
  in_cca: boolean
  program: CCAProgram | null
}

export interface CCACompareResponse {
  cca_id: string
  program_name: string
  provider: string
  default_rate: number
  cca_rate: number
  rate_difference_pct: number
  savings_per_kwh: number
  estimated_monthly_savings: number
  is_cheaper: boolean
}

export interface CCAListResponse {
  count: number
  programs: CCAProgram[]
}

export async function detectCCA(params: {
  zip_code?: string
  state?: string
  municipality?: string
}): Promise<CCADetectResponse> {
  return apiClient.get<CCADetectResponse>('/cca/detect', params)
}

export async function compareCCARate(
  ccaId: string,
  defaultRate: number,
): Promise<CCACompareResponse> {
  return apiClient.get<CCACompareResponse>(`/cca/compare/${ccaId}`, {
    default_rate: defaultRate,
  })
}

export async function getCCAInfo(ccaId: string): Promise<CCAProgram> {
  return apiClient.get<CCAProgram>(`/cca/info/${ccaId}`)
}

export async function listCCAPrograms(
  state?: string,
): Promise<CCAListResponse> {
  return apiClient.get<CCAListResponse>('/cca/programs', state ? { state } : {})
}
