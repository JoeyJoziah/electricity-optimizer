import { useQuery } from '@tanstack/react-query'
import {
  detectCCA,
  compareCCARate,
  getCCAInfo,
  listCCAPrograms,
} from '../api/cca'

export function useCCADetect(zipCode?: string, state?: string) {
  return useQuery({
    queryKey: ['cca', 'detect', zipCode, state],
    queryFn: ({ signal }) => detectCCA({ zip_code: zipCode, state }, signal),
    enabled: !!zipCode || !!state,
    staleTime: 1000 * 60 * 60, // 1 hour
  })
}

export function useCCACompare(ccaId?: string, defaultRate?: number) {
  return useQuery({
    queryKey: ['cca', 'compare', ccaId, defaultRate],
    queryFn: ({ signal }) => compareCCARate(ccaId!, defaultRate!, signal),
    enabled: !!ccaId && !!defaultRate && defaultRate > 0,
    staleTime: 1000 * 60 * 60,
  })
}

export function useCCAInfo(ccaId?: string) {
  return useQuery({
    queryKey: ['cca', 'info', ccaId],
    queryFn: ({ signal }) => getCCAInfo(ccaId!, signal),
    enabled: !!ccaId,
    staleTime: 1000 * 60 * 60,
  })
}

export function useCCAPrograms(state?: string) {
  return useQuery({
    queryKey: ['cca', 'programs', state],
    queryFn: ({ signal }) => listCCAPrograms(state, signal),
    staleTime: 1000 * 60 * 60,
  })
}
