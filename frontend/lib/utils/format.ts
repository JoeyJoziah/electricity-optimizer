import { format, formatDistanceToNow, parseISO } from 'date-fns'

/**
 * Format a number as currency
 */
export function formatCurrency(
  amount: number,
  currency: 'USD' | 'GBP' | 'EUR' = 'USD'
): string {
  const symbols: Record<string, string> = {
    GBP: '\u00A3',
    EUR: '\u20AC',
    USD: '$',
  }

  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(amount))

  const sign = amount < 0 ? '-' : ''
  return `${sign}${symbols[currency]}${formatted}`
}

/**
 * Format a price per kWh
 */
export function formatPricePerKwh(price: number, currency: 'USD' | 'GBP' | 'EUR' = 'USD'): string {
  return `${formatCurrency(price, currency)}/kWh`
}

/**
 * Format a percentage
 */
export function formatPercentage(value: number, decimals: number = 2): string {
  return `${value.toFixed(decimals)}%`
}

/**
 * Format a date/time string
 */
export function formatDateTime(
  dateString: string,
  formatStr: string = 'dd MMM yyyy HH:mm'
): string {
  try {
    const date = parseISO(dateString)
    return format(date, formatStr)
  } catch {
    return dateString
  }
}

/**
 * Format time only
 */
export function formatTime(dateString: string, is24Hour: boolean = true): string {
  const date = parseISO(dateString)
  return format(date, is24Hour ? 'HH:mm' : 'h:mm a')
}

/**
 * Format date only
 */
export function formatDate(dateString: string): string {
  const date = parseISO(dateString)
  return format(date, 'dd MMM yyyy')
}

/**
 * Format relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(dateString: string): string {
  const date = parseISO(dateString)
  return formatDistanceToNow(date, { addSuffix: true })
}

/**
 * Format a large number with abbreviations (e.g., 1.2K, 3.5M)
 */
export function formatCompactNumber(num: number): string {
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(1)}M`
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}K`
  }
  return num.toString()
}

/**
 * Format energy consumption in kWh
 */
export function formatEnergy(kWh: number): string {
  if (kWh >= 1000) {
    return `${(kWh / 1000).toFixed(2)} MWh`
  }
  return `${kWh.toFixed(2)} kWh`
}

/**
 * Format duration in hours and minutes
 */
export function formatDuration(hours: number): string {
  const wholeHours = Math.floor(hours)
  const minutes = Math.round((hours - wholeHours) * 60)

  if (wholeHours === 0) {
    return `${minutes}m`
  }
  if (minutes === 0) {
    return `${wholeHours}h`
  }
  return `${wholeHours}h ${minutes}m`
}
