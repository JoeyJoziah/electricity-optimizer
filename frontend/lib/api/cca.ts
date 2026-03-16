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

export async function detectCCA(
  params: {
    zip_code?: string
    state?: string
    municipality?: string
  },
  signal?: AbortSignal,
): Promise<CCADetectResponse> {
  return apiClient.get<CCADetectResponse>('/cca/detect', params, { signal })
}

export async function compareCCARate(
  ccaId: string,
  defaultRate: number,
  signal?: AbortSignal,
): Promise<CCACompareResponse> {
  return apiClient.get<CCACompareResponse>(`/cca/compare/${ccaId}`, {
    default_rate: defaultRate,
  }, { signal })
}

export async function getCCAInfo(
  ccaId: string,
  signal?: AbortSignal,
): Promise<CCAProgram> {
  return apiClient.get<CCAProgram>(`/cca/info/${ccaId}`, undefined, { signal })
}

export async function listCCAPrograms(
  state?: string,
  signal?: AbortSignal,
): Promise<CCAListResponse> {
  return apiClient.get<CCAListResponse>('/cca/programs', state ? { state } : {}, { signal })
}
