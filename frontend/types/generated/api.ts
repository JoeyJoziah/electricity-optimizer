/**
 * Auto-generated TypeScript types from the FastAPI OpenAPI spec.
 *
 * DO NOT EDIT MANUALLY.
 * Regenerate with: npm run generate-types  (requires backend running)
 *                  npm run generate-types:offline  (from saved openapi.json)
 *
 * Generated at: 2026-03-10T00:00:00Z
 * Source: backend FastAPI /openapi.json
 */

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

/**
 * Decimal values are serialised as strings by the backend
 * (FastAPI + Pydantic with json_encoders={Decimal: str}).
 * Parse with parseFloat() / Number() before arithmetic.
 */
export type DecimalStr = string

/** ISO-8601 datetime string with timezone offset */
export type DateTimeStr = string

// ---------------------------------------------------------------------------
// Enums (mirrored from backend Python enums)
// ---------------------------------------------------------------------------

export type TariffType =
  | 'fixed'
  | 'variable'
  | 'time_of_use'
  | 'prepaid'
  | 'green'
  | 'agile'

export type ContractLength =
  | 'monthly'
  | 'annual'
  | 'two_year'
  | 'three_year'
  | 'rolling'

export type EnergySource =
  | 'renewable'
  | 'fossil'
  | 'nuclear'
  | 'mixed'

export type UtilityType =
  | 'electricity'
  | 'natural_gas'
  | 'heating_oil'
  | 'propane'
  | 'community_solar'

export type SubscriptionTier = 'free' | 'pro' | 'business'

// ---------------------------------------------------------------------------
// Price schemas  (backend: models/price.py + api/v1/prices.py)
// ---------------------------------------------------------------------------

/**
 * Single electricity price record (maps to backend Price model).
 * price_per_kwh is a Decimal string — parse before arithmetic.
 */
export interface ApiPrice {
  id: string
  region: string
  supplier: string
  /** Decimal string, e.g. "0.2400" */
  price_per_kwh: DecimalStr
  timestamp: DateTimeStr
  currency: string
  utility_type: UtilityType
  unit: string
  is_peak: boolean | null
  carbon_intensity: number | null
  energy_source: EnergySource | null
  tariff_name: string | null
  /** Decimal string */
  energy_cost: DecimalStr | null
  /** Decimal string */
  network_cost: DecimalStr | null
  /** Decimal string */
  taxes: DecimalStr | null
  /** Decimal string */
  levies: DecimalStr | null
  source_api: string | null
  created_at: DateTimeStr
}

/**
 * Summarised price used in list/comparison responses.
 * Returned by GET /prices/current (inside prices[]) and GET /prices/compare.
 */
export interface ApiPriceResponse {
  /** e.g. "ELEC-US_CT" */
  ticker: string
  /** Decimal string */
  current_price: DecimalStr
  currency: string
  region: string
  supplier: string
  updated_at: DateTimeStr
  is_peak: boolean | null
  carbon_intensity: number | null
  /** Decimal string */
  price_change_24h: DecimalStr | null
}

/**
 * Response from GET /prices/current
 */
export interface ApiCurrentPriceResponse {
  /** Present when a specific supplier was requested */
  price: ApiPriceResponse | null
  /** Present when listing all suppliers in region */
  prices: ApiPriceResponse[] | null
  region: string
  timestamp: DateTimeStr
  source: string | null
}

/**
 * Response from GET /prices/history
 */
export interface ApiPriceHistoryResponse {
  region: string
  supplier: string | null
  start_date: DateTimeStr
  end_date: DateTimeStr
  /** Full Price objects (includes price_per_kwh, timestamp, etc.) */
  prices: ApiPrice[]
  /** Decimal string */
  average_price: DecimalStr | null
  /** Decimal string */
  min_price: DecimalStr | null
  /** Decimal string */
  max_price: DecimalStr | null
  source: string | null
  total: number
  page: number
  page_size: number
  pages: number
}

/**
 * Price forecast container (maps to backend PriceForecast model).
 */
export interface ApiPriceForecastModel {
  id: string
  region: string
  generated_at: DateTimeStr
  horizon_hours: number
  /** Array of full ApiPrice objects */
  prices: ApiPrice[]
  confidence: number
  model_version: string | null
  source_api: string | null
}

/**
 * Response from GET /prices/forecast
 */
export interface ApiPriceForecastResponse {
  region: string
  forecast: ApiPriceForecastModel
  generated_at: DateTimeStr
  horizon_hours: number
  confidence: number
  source: string | null
}

/**
 * Response from GET /prices/compare
 */
export interface ApiPriceComparisonResponse {
  region: string
  timestamp: DateTimeStr
  suppliers: ApiPriceResponse[]
  cheapest_supplier: string
  /** Decimal string */
  cheapest_price: DecimalStr
  /** Decimal string */
  average_price: DecimalStr
  source: string | null
}

// ---------------------------------------------------------------------------
// Supplier schemas  (backend: models/supplier.py + api/v1/suppliers.py)
// ---------------------------------------------------------------------------

/**
 * Supplier contact information.
 */
export interface ApiSupplierContact {
  email: string | null
  phone: string | null
  website: string | null
  support_hours: string | null
  address: string | null
}

/**
 * Summary supplier record — returned in list responses.
 * Maps to backend SupplierResponse.
 */
export interface ApiSupplierResponse {
  id: string
  name: string
  regions: string[]
  tariff_types: string[]
  api_available: boolean
  rating: number | null
  green_energy_provider: boolean
  is_active: boolean
}

/**
 * Full supplier details — returned by GET /suppliers/{id}.
 * Maps to backend SupplierDetailResponse.
 */
export interface ApiSupplierDetailResponse {
  id: string
  name: string
  regions: string[]
  tariff_types: string[]
  api_available: boolean
  contact: ApiSupplierContact | null
  rating: number | null
  review_count: number | null
  green_energy_provider: boolean
  carbon_neutral: boolean
  average_renewable_percentage: number | null
  description: string | null
  logo_url: string | null
  is_active: boolean
}

/**
 * Paginated supplier list — returned by GET /suppliers and GET /suppliers/region/{region}.
 * Maps to backend SuppliersResponse (api/v1/suppliers.py).
 */
export interface ApiSuppliersListResponse {
  suppliers: ApiSupplierResponse[]
  total: number
  page: number
  page_size: number
  region: string | null
  utility_type: string | null
}

/**
 * Tariff record — returned inside SupplierTariffsResponse.
 */
export interface ApiTariffResponse {
  id: string
  supplier_id: string
  name: string
  type: TariffType
  /** Decimal string */
  unit_rate: DecimalStr
  /** Decimal string */
  standing_charge: DecimalStr
  green_energy_percentage: number
  contract_length: ContractLength
  is_available: boolean
}

/**
 * Response from GET /suppliers/{id}/tariffs.
 */
export interface ApiSupplierTariffsResponse {
  supplier_id: string
  supplier_name: string
  tariffs: ApiTariffResponse[]
  total: number
}

/**
 * Registry supplier entry — returned by GET /suppliers/registry.
 * Lightweight shape used for the DirectLoginForm dropdown.
 */
export interface ApiRegistrySupplierEntry {
  id: string
  name: string
  region: string | null
  utility_type: string
}

export interface ApiRegistryResponse {
  suppliers: ApiRegistrySupplierEntry[]
}

// ---------------------------------------------------------------------------
// User schemas  (backend: models/user.py)
// ---------------------------------------------------------------------------

/**
 * Public user response (no sensitive fields).
 * Maps to backend UserResponse.
 */
export interface ApiUserResponse {
  id: string
  email: string
  name: string
  region: string | null
  is_active: boolean
  is_verified: boolean
  current_supplier: string | null
  current_tariff: string | null
  created_at: DateTimeStr
}

/**
 * User preferences — maps to backend UserPreferences model.
 */
export interface ApiUserPreferences {
  notification_enabled: boolean
  email_notifications: boolean
  push_notifications: boolean
  /** "immediate" | "hourly" | "daily" | "weekly" */
  notification_frequency: string
  /** Decimal string */
  cost_threshold: DecimalStr | null
  /** Decimal string */
  budget_limit_daily: DecimalStr | null
  /** Decimal string */
  budget_limit_monthly: DecimalStr | null
  auto_switch_enabled: boolean
  /** Decimal string */
  auto_switch_threshold: DecimalStr | null
  preferred_suppliers: string[]
  excluded_suppliers: string[]
  green_energy_only: boolean
  min_renewable_percentage: number
  peak_avoidance_enabled: boolean
  preferred_usage_hours: number[]
  price_alert_enabled: boolean
  /** Decimal string */
  price_alert_below: DecimalStr | null
  /** Decimal string */
  price_alert_above: DecimalStr | null
  alert_optimal_windows: boolean
}

/**
 * Response from GET /user/preferences.
 * Maps to backend UserPreferencesResponse.
 */
export interface ApiUserPreferencesResponse {
  user_id: string
  preferences: ApiUserPreferences
  updated_at: DateTimeStr
}

// ---------------------------------------------------------------------------
// User-Supplier linking schemas  (backend: api/v1/user.py)
// ---------------------------------------------------------------------------

/**
 * The user's current supplier — returned by GET /user/supplier and
 * PUT /user/supplier.
 */
export interface ApiUserSupplierResponse {
  supplier_id: string
  supplier_name: string
  regions: string[]
  rating: number | null
  green_energy: boolean
  website: string | null
}

/**
 * Request body for PUT /user/supplier.
 */
export interface ApiSetUserSupplierRequest {
  supplier_id: string
}

/**
 * Request body for POST /user/supplier/link.
 */
export interface ApiLinkAccountRequest {
  supplier_id: string
  account_number: string
  meter_number?: string
  service_zip?: string
  account_nickname?: string
  consent_given: boolean
}

/**
 * A linked supplier account (masked) — returned by POST /user/supplier/link
 * and inside GET /user/supplier/accounts.
 */
export interface ApiLinkedAccountResponse {
  supplier_id: string
  supplier_name: string
  account_number_masked: string | null
  meter_number_masked: string | null
  service_zip: string | null
  account_nickname: string | null
  is_primary: boolean
  verified_at: DateTimeStr | null
  created_at: DateTimeStr
}

// ---------------------------------------------------------------------------
// Generic API error shape (FastAPI default)
// ---------------------------------------------------------------------------

export interface ApiValidationError {
  detail: Array<{
    loc: Array<string | number>
    msg: string
    type: string
  }>
}

export interface ApiErrorDetail {
  detail: string
}
