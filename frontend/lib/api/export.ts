import { apiClient } from './client'

export interface ExportResponse {
  format: 'json' | 'csv'
  content_type: string
  data: Record<string, unknown>[] | string
  count: number
  utility_type: string
  unit: string
  date_range: {
    start: string
    end: string
  }
  error?: string
}

export interface ExportTypesResponse {
  supported_types: string[]
  formats: string[]
  max_days: number
  max_rows: number
}

export async function exportRates(
  utilityType: string,
  format: 'json' | 'csv' = 'json',
  state?: string,
  startDate?: string,
  endDate?: string,
): Promise<ExportResponse> {
  const params: Record<string, string> = {
    utility_type: utilityType,
    format,
  }
  if (state) params.state = state
  if (startDate) params.start_date = startDate
  if (endDate) params.end_date = endDate
  return apiClient.get<ExportResponse>('/export/rates', params)
}

export async function getExportTypes(): Promise<ExportTypesResponse> {
  return apiClient.get<ExportTypesResponse>('/export/types')
}
