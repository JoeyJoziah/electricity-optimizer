/**
 * Core type definitions for the Electricity Optimizer frontend
 */

// Price data types
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
