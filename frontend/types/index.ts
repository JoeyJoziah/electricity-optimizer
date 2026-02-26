/**
 * Core type definitions for the Electricity Optimizer frontend
 */

// ---------------------------------------------------------------------------
// Raw API response shapes (backend field names before frontend normalization)
// ---------------------------------------------------------------------------

/**
 * A single price entry as returned by the backend /prices endpoints.
 * The backend may use either frontend-friendly names (price, time) or
 * database column names (price_per_kwh, timestamp).
 */
export interface RawPricePoint {
  /** Frontend-friendly field (normalized by price service) */
  price?: number | null
  /** Database column name from electricity_prices table */
  price_per_kwh?: number | null
  /** Frontend-friendly timestamp field */
  time?: string | number
  /** Database column name */
  timestamp?: string | number
  /** Forecast flag on history records */
  forecast?: number | null
  /** Percentage change over 24 h (frontend-friendly) */
  changePercent?: number | null
  /** Percentage change over 24 h (backend field name) */
  price_change_24h?: number | null
  trend?: 'increasing' | 'decreasing' | 'stable'
  region?: string
  supplier?: string
}

/**
 * A single forecast price entry inside a forecast array.
 * May come from an object with a nested `prices` array (backend shape) or
 * a flat array of ForecastPoint objects (frontend shape).
 */
export interface RawForecastPriceEntry {
  price?: number | null
  price_per_kwh?: number | null
  timestamp?: string
}

/**
 * Raw backend supplier record before field normalization.
 * The backend returns snake_case names; the frontend Supplier type uses camelCase.
 */
export interface RawSupplierRecord {
  id: string
  name: string
  /** Backend field */
  logo_url?: string
  /** Frontend-normalized field */
  logo?: string
  /** Frontend camelCase */
  avgPricePerKwh?: number
  /** Frontend camelCase */
  standingCharge?: number
  /** Frontend camelCase */
  greenEnergy?: boolean
  /** Backend snake_case */
  green_energy_provider?: boolean
  rating?: number
  /** Frontend camelCase */
  estimatedAnnualCost?: number
  /** Frontend camelCase */
  tariffType?: 'fixed' | 'variable' | 'time-of-use'
  /** Backend array of tariff type strings */
  tariff_types?: string[]
  /** Frontend camelCase */
  exitFee?: number
  /** Backend snake_case */
  exit_fee?: number
  /** Frontend camelCase */
  contractLength?: number
  /** Backend snake_case */
  contract_length?: number
  features?: string[]
}

// ---------------------------------------------------------------------------
// Price data types
// ---------------------------------------------------------------------------

export interface PriceDataPoint {
  time: string
  price: number | null
  forecast: number | null
  isOptimal?: boolean
  confidenceLow?: number
  confidenceHigh?: number
}

export interface CurrentPrice {
  region: string
  price: number
  timestamp: string
  trend: 'increasing' | 'decreasing' | 'stable'
  changePercent: number
}

export interface PriceForecast {
  hour: number
  price: number
  confidence: [number, number]
  timestamp: string
}

// Supplier types
export interface Supplier {
  id: string
  name: string
  logo?: string
  avgPricePerKwh: number
  standingCharge: number
  greenEnergy: boolean
  rating: number
  estimatedAnnualCost: number
  exitFee?: number
  tariffType: 'fixed' | 'variable' | 'time-of-use'
  contractLength?: number
  features?: string[]
}

export interface SupplierRecommendation {
  supplier: Supplier
  currentSupplier: Supplier
  estimatedSavings: number
  paybackMonths: number
  confidence: number
}

// Optimization types
export interface Appliance {
  id: string
  name: string
  powerKw: number
  typicalDurationHours: number
  isFlexible: boolean
  preferredTimeRange?: {
    start: number
    end: number
  }
  priority: 'high' | 'medium' | 'low'
}

export interface OptimizationSchedule {
  applianceId: string
  applianceName: string
  scheduledStart: string
  scheduledEnd: string
  estimatedCost: number
  savings: number
  reason: string
}

export interface OptimizationResult {
  schedules: OptimizationSchedule[]
  totalSavings: number
  totalCost: number
  optimalPeriods: {
    start: string
    end: string
    avgPrice: number
  }[]
}

// User settings types
export interface UserSettings {
  region: string
  currentSupplier: Supplier | null
  annualUsageKwh: number
  peakDemandKw: number
  appliances: Appliance[]
  notificationPreferences: {
    priceAlerts: boolean
    optimalTimes: boolean
    supplierUpdates: boolean
  }
  displayPreferences: {
    currency: 'USD' | 'GBP' | 'EUR'
    theme: 'light' | 'dark' | 'system'
    timeFormat: '12h' | '24h'
  }
}

// Dashboard widget types
export interface DashboardSummary {
  currentPrice: CurrentPrice
  todaySavings: number
  monthSavings: number
  totalSavings: number
  nextOptimalPeriod: {
    start: string
    end: string
    price: number
  } | null
  supplierRecommendation: SupplierRecommendation | null
}

// API response types
export interface ApiResponse<T> {
  data: T
  success: boolean
  error?: string
  timestamp: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  hasMore: boolean
}

// Chart configuration types
export interface ChartConfig {
  showForecast?: boolean
  highlightOptimal?: boolean
  timeRange?: '6h' | '12h' | '24h' | '48h' | '7d'
  showVolume?: boolean
  showConfidence?: boolean
}

// Form types
export interface SwitchWizardState {
  step: 1 | 2 | 3 | 4
  recommendation: SupplierRecommendation
  gdprConsent: boolean
  contractAccepted: boolean
  isSubmitting: boolean
  error?: string
}

// Event types
export type TimeRange = '6h' | '12h' | '24h' | '48h' | '7d'
