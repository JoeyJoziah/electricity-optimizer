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
    queryFn: () => detectCCA({ zip_code: zipCode, state }),
    enabled: !!zipCode || !!state,
    staleTime: 1000 * 60 * 60, // 1 hour
  })
}

export function useCCACompare(ccaId?: string, defaultRate?: number) {
  return useQuery({
    queryKey: ['cca', 'compare', ccaId, defaultRate],
    queryFn: () => compareCCARate(ccaId!, defaultRate!),
    enabled: !!ccaId && !!defaultRate && defaultRate > 0,
    staleTime: 1000 * 60 * 60,
  })
}

export function useCCAInfo(ccaId?: string) {
  return useQuery({
    queryKey: ['cca', 'info', ccaId],
    queryFn: () => getCCAInfo(ccaId!),
    enabled: !!ccaId,
    staleTime: 1000 * 60 * 60,
  })
}

export function useCCAPrograms(state?: string) {
  return useQuery({
    queryKey: ['cca', 'programs', state],
    queryFn: () => listCCAPrograms(state),
    staleTime: 1000 * 60 * 60,
  })
}
