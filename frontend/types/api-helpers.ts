/**
 * API type helpers — bridges generated backend types to frontend conventions.
 *
 * This file provides:
 *  - Friendly re-exports with camelCase aliases
 *  - Decimal → number parsing helpers
 *  - Type narrowing / discriminated-union helpers
 *  - Normalisation functions (snake_case → camelCase for UI components)
 *
 * Import generated types directly for strict backend shapes.
 * Import from here for UI-layer consumption where camelCase is preferred.
 */

import type {
  ApiCurrentPriceResponse,
  ApiPriceResponse,
  ApiPriceHistoryResponse,
  ApiPriceForecastResponse,
  ApiPriceComparisonResponse,
  ApiSupplierResponse,
  ApiSupplierDetailResponse,
  ApiSuppliersListResponse,
  ApiTariffResponse,
  ApiSupplierTariffsResponse,
  ApiRegistrySupplierEntry,
  ApiUserResponse,
  ApiUserSupplierResponse,
  ApiLinkedAccountResponse,
  ApiErrorDetail,
  ApiValidationError,
  DecimalStr,
  TariffType,
} from './generated/api'

// ---------------------------------------------------------------------------
// Re-exports with friendly aliases
// ---------------------------------------------------------------------------

export type {
  ApiCurrentPriceResponse,
  ApiPriceResponse,
  ApiPriceHistoryResponse,
  ApiPriceForecastResponse,
  ApiPriceComparisonResponse,
  ApiSupplierResponse,
  ApiSupplierDetailResponse,
  ApiSuppliersListResponse,
  ApiTariffResponse,
  ApiSupplierTariffsResponse,
  ApiRegistrySupplierEntry,
  ApiUserResponse,
  ApiUserSupplierResponse,
  ApiLinkedAccountResponse,
  ApiErrorDetail,
  ApiValidationError,
}

// ---------------------------------------------------------------------------
// Decimal parsing helpers
//
// The backend serialises Decimal fields as strings to avoid IEEE-754 drift.
// Parse them before displaying or performing arithmetic.
// ---------------------------------------------------------------------------

/**
 * Parse a Decimal string from the backend into a JS number.
 * Returns null when the input is null / undefined.
 *
 * @example
 *   parseDecimal("0.2400")  // => 0.24
 *   parseDecimal(null)      // => null
 */
export function parseDecimal(value: DecimalStr | null | undefined): number | null {
  if (value === null || value === undefined) return null
  const parsed = parseFloat(value)
  return isNaN(parsed) ? null : parsed
}

/**
 * Parse a Decimal string and fall back to a default when null.
 *
 * @example
 *   parseDecimalOr("0.2400", 0)  // => 0.24
 *   parseDecimalOr(null, 0)      // => 0
 */
export function parseDecimalOr(value: DecimalStr | null | undefined, fallback: number): number {
  return parseDecimal(value) ?? fallback
}

// ---------------------------------------------------------------------------
// Price normalisation
//
// Maps the backend's snake_case ApiPriceResponse to the camelCase shape
// that existing UI components (PriceChart, DashboardContent, etc.) expect.
// ---------------------------------------------------------------------------

/** Normalised price point consumed by UI chart components */
export interface NormalisedPricePoint {
  time: string
  price: number | null
  forecast: number | null
  isOptimal?: boolean
  confidenceLow?: number
  confidenceHigh?: number
  supplier: string
  region: string
  isPeak: boolean | null
  carbonIntensity: number | null
  currency: string
}

/** Normalised "current price" card data */
export interface NormalisedCurrentPrice {
  region: string
  price: number
  timestamp: string
  supplier: string
  isPeak: boolean | null
  carbonIntensity: number | null
  currency: string
  /** Percentage change over 24 h — may be null if backend omits it */
  priceChange24h: number | null
}

/**
 * Normalise a single ApiPriceResponse (from /prices/current or /prices/compare)
 * into the camelCase shape used by UI components.
 */
export function normalisePriceResponse(raw: ApiPriceResponse): NormalisedCurrentPrice {
  return {
    region: raw.region,
    price: parseDecimalOr(raw.current_price, 0),
    timestamp: raw.updated_at,
    supplier: raw.supplier,
    isPeak: raw.is_peak,
    carbonIntensity: raw.carbon_intensity,
    currency: raw.currency,
    priceChange24h: parseDecimal(raw.price_change_24h),
  }
}

// ---------------------------------------------------------------------------
// Supplier normalisation
//
// Maps the backend's ApiSupplierResponse / ApiSupplierDetailResponse to the
// camelCase Supplier shape used by UI components.
// ---------------------------------------------------------------------------

/**
 * Normalised supplier shape consumed by supplier list / comparison UI.
 * Mirrors the existing frontend `Supplier` type in types/index.ts but
 * derives from generated API types for correctness.
 */
export interface NormalisedSupplier {
  id: string
  name: string
  logoUrl: string | null
  regions: string[]
  tariffTypes: string[]
  apiAvailable: boolean
  rating: number | null
  reviewCount: number | null
  greenEnergyProvider: boolean
  carbonNeutral: boolean
  averageRenewablePercentage: number | null
  description: string | null
  isActive: boolean
}

/**
 * Normalise an ApiSupplierResponse (list endpoint) into the camelCase shape.
 */
export function normaliseSupplierResponse(raw: ApiSupplierResponse): NormalisedSupplier {
  return {
    id: raw.id,
    name: raw.name,
    logoUrl: null,
    regions: raw.regions,
    tariffTypes: raw.tariff_types,
    apiAvailable: raw.api_available,
    rating: raw.rating,
    reviewCount: null,
    greenEnergyProvider: raw.green_energy_provider,
    carbonNeutral: false,
    averageRenewablePercentage: null,
    description: null,
    isActive: raw.is_active,
  }
}

/**
 * Normalise an ApiSupplierDetailResponse (detail endpoint) into the camelCase shape.
 */
export function normaliseSupplierDetailResponse(raw: ApiSupplierDetailResponse): NormalisedSupplier {
  return {
    id: raw.id,
    name: raw.name,
    logoUrl: raw.logo_url,
    regions: raw.regions,
    tariffTypes: raw.tariff_types,
    apiAvailable: raw.api_available,
    rating: raw.rating,
    reviewCount: raw.review_count,
    greenEnergyProvider: raw.green_energy_provider,
    carbonNeutral: raw.carbon_neutral,
    averageRenewablePercentage: raw.average_renewable_percentage,
    description: raw.description,
    isActive: raw.is_active,
  }
}

// ---------------------------------------------------------------------------
// Tariff normalisation
// ---------------------------------------------------------------------------

/** Normalised tariff record */
export interface NormalisedTariff {
  id: string
  supplierId: string
  name: string
  type: TariffType
  unitRate: number
  standingCharge: number
  greenEnergyPercentage: number
  contractLength: string
  isAvailable: boolean
}

export function normaliseTariffResponse(raw: ApiTariffResponse): NormalisedTariff {
  return {
    id: raw.id,
    supplierId: raw.supplier_id,
    name: raw.name,
    type: raw.type,
    unitRate: parseDecimalOr(raw.unit_rate, 0),
    standingCharge: parseDecimalOr(raw.standing_charge, 0),
    greenEnergyPercentage: raw.green_energy_percentage,
    contractLength: raw.contract_length,
    isAvailable: raw.is_available,
  }
}

// ---------------------------------------------------------------------------
// Type guards
// ---------------------------------------------------------------------------

/**
 * Narrow an unknown error response to the FastAPI validation error shape
 * (HTTP 422 with a `detail` array).
 */
export function isValidationError(value: unknown): value is ApiValidationError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'detail' in value &&
    Array.isArray((value as ApiValidationError).detail)
  )
}

/**
 * Narrow an unknown error response to the simple FastAPI error detail shape
 * (HTTP 4xx/5xx with a `detail` string).
 */
export function isApiErrorDetail(value: unknown): value is ApiErrorDetail {
  return (
    typeof value === 'object' &&
    value !== null &&
    'detail' in value &&
    typeof (value as ApiErrorDetail).detail === 'string'
  )
}

/**
 * Type-safe extraction of an error message from a FastAPI error response.
 * Falls back to a generic message when the shape is unexpected.
 */
export function extractApiErrorMessage(value: unknown, fallback = 'An unexpected error occurred'): string {
  if (isApiErrorDetail(value)) return value.detail
  if (isValidationError(value)) {
    const first = value.detail[0]
    return first ? `${first.loc.join('.')}: ${first.msg}` : fallback
  }
  if (value instanceof Error) return value.message
  return fallback
}

// ---------------------------------------------------------------------------
// Pagination helpers
// ---------------------------------------------------------------------------

export interface PaginationMeta {
  total: number
  page: number
  pageSize: number
  pages: number
  hasMore: boolean
}

/**
 * Extract pagination metadata from a history/list response.
 */
export function extractPaginationMeta(
  response: Pick<ApiPriceHistoryResponse | ApiSuppliersListResponse, 'total' | 'page' | 'page_size'> & {
    pages?: number
  }
): PaginationMeta {
  const pages = 'pages' in response && response.pages != null
    ? response.pages
    : Math.max(1, Math.ceil(response.total / response.page_size))

  return {
    total: response.total,
    page: response.page,
    pageSize: response.page_size,
    pages,
    hasMore: response.page < pages,
  }
}
