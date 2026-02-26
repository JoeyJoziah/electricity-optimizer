/**
 * US States & Regions — Single source of truth
 *
 * All 50 states + DC, grouped by census region.
 * Reused by Settings page, Onboarding, and anywhere else that needs a state picker.
 */

export interface StateOption {
  value: string    // e.g. 'us_ct'
  label: string    // e.g. 'Connecticut'
  abbr: string     // e.g. 'CT'
}

export interface RegionGroup {
  label: string
  states: StateOption[]
}

export const DEREGULATED_ELECTRICITY_STATES = new Set([
  'CT', 'TX', 'OH', 'PA', 'IL', 'NY', 'NJ', 'MA', 'MD', 'RI',
  'NH', 'ME', 'DE', 'MI', 'VA', 'DC', 'OR', 'MT',
])

export const US_REGIONS: RegionGroup[] = [
  {
    label: 'Northeast',
    states: [
      { value: 'us_ct', label: 'Connecticut', abbr: 'CT' },
      { value: 'us_de', label: 'Delaware', abbr: 'DE' },
      { value: 'us_dc', label: 'District of Columbia', abbr: 'DC' },
      { value: 'us_me', label: 'Maine', abbr: 'ME' },
      { value: 'us_md', label: 'Maryland', abbr: 'MD' },
      { value: 'us_ma', label: 'Massachusetts', abbr: 'MA' },
      { value: 'us_nh', label: 'New Hampshire', abbr: 'NH' },
      { value: 'us_nj', label: 'New Jersey', abbr: 'NJ' },
      { value: 'us_ny', label: 'New York', abbr: 'NY' },
      { value: 'us_pa', label: 'Pennsylvania', abbr: 'PA' },
      { value: 'us_ri', label: 'Rhode Island', abbr: 'RI' },
      { value: 'us_vt', label: 'Vermont', abbr: 'VT' },
    ],
  },
  {
    label: 'Southeast',
    states: [
      { value: 'us_al', label: 'Alabama', abbr: 'AL' },
      { value: 'us_ar', label: 'Arkansas', abbr: 'AR' },
      { value: 'us_fl', label: 'Florida', abbr: 'FL' },
      { value: 'us_ga', label: 'Georgia', abbr: 'GA' },
      { value: 'us_ky', label: 'Kentucky', abbr: 'KY' },
      { value: 'us_la', label: 'Louisiana', abbr: 'LA' },
      { value: 'us_ms', label: 'Mississippi', abbr: 'MS' },
      { value: 'us_nc', label: 'North Carolina', abbr: 'NC' },
      { value: 'us_sc', label: 'South Carolina', abbr: 'SC' },
      { value: 'us_tn', label: 'Tennessee', abbr: 'TN' },
      { value: 'us_va', label: 'Virginia', abbr: 'VA' },
      { value: 'us_wv', label: 'West Virginia', abbr: 'WV' },
    ],
  },
  {
    label: 'Midwest',
    states: [
      { value: 'us_il', label: 'Illinois', abbr: 'IL' },
      { value: 'us_in', label: 'Indiana', abbr: 'IN' },
      { value: 'us_ia', label: 'Iowa', abbr: 'IA' },
      { value: 'us_ks', label: 'Kansas', abbr: 'KS' },
      { value: 'us_mi', label: 'Michigan', abbr: 'MI' },
      { value: 'us_mn', label: 'Minnesota', abbr: 'MN' },
      { value: 'us_mo', label: 'Missouri', abbr: 'MO' },
      { value: 'us_ne', label: 'Nebraska', abbr: 'NE' },
      { value: 'us_nd', label: 'North Dakota', abbr: 'ND' },
      { value: 'us_oh', label: 'Ohio', abbr: 'OH' },
      { value: 'us_sd', label: 'South Dakota', abbr: 'SD' },
      { value: 'us_wi', label: 'Wisconsin', abbr: 'WI' },
    ],
  },
  {
    label: 'South Central',
    states: [
      { value: 'us_ok', label: 'Oklahoma', abbr: 'OK' },
      { value: 'us_tx', label: 'Texas', abbr: 'TX' },
    ],
  },
  {
    label: 'West',
    states: [
      { value: 'us_ak', label: 'Alaska', abbr: 'AK' },
      { value: 'us_az', label: 'Arizona', abbr: 'AZ' },
      { value: 'us_ca', label: 'California', abbr: 'CA' },
      { value: 'us_co', label: 'Colorado', abbr: 'CO' },
      { value: 'us_hi', label: 'Hawaii', abbr: 'HI' },
      { value: 'us_id', label: 'Idaho', abbr: 'ID' },
      { value: 'us_mt', label: 'Montana', abbr: 'MT' },
      { value: 'us_nv', label: 'Nevada', abbr: 'NV' },
      { value: 'us_nm', label: 'New Mexico', abbr: 'NM' },
      { value: 'us_or', label: 'Oregon', abbr: 'OR' },
      { value: 'us_ut', label: 'Utah', abbr: 'UT' },
      { value: 'us_wa', label: 'Washington', abbr: 'WA' },
      { value: 'us_wy', label: 'Wyoming', abbr: 'WY' },
    ],
  },
  {
    label: 'International',
    states: [
      { value: 'uk', label: 'United Kingdom', abbr: 'UK' },
      { value: 'de', label: 'Germany', abbr: 'DE' },
      { value: 'fr', label: 'France', abbr: 'FR' },
    ],
  },
]

/** Flat list of all state options */
export const ALL_STATES: StateOption[] = US_REGIONS.flatMap((g) => g.states)

/** Lookup map: value -> label */
export const STATE_LABELS: Record<string, string> = Object.fromEntries(
  ALL_STATES.map((s) => [s.value, s.label])
)
