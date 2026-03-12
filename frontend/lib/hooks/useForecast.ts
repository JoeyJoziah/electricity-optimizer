import { useQuery } from '@tanstack/react-query'
import { getForecast, getForecastTypes } from '../api/forecast'

export function useForecast(
  utilityType?: string,
  state?: string,
  horizonDays?: number,
) {
  return useQuery({
    queryKey: ['forecast', utilityType, state, horizonDays],
    queryFn: () => getForecast(utilityType!, state, horizonDays),
    enabled: !!utilityType,
    staleTime: 1000 * 60 * 30, // 30 minutes
  })
}

export function useForecastTypes() {
  return useQuery({
    queryKey: ['forecast', 'types'],
    queryFn: getForecastTypes,
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
  })
}
