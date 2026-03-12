/**
 * SEO constants for programmatic rate pages.
 */

export const US_STATES: Record<string, string> = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas',
  CA: 'California', CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware',
  DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii',
  ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa',
  KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine',
  MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota',
  MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska',
  NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico',
  NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio',
  OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island',
  SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas',
  UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington',
  WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming',
}

export const UTILITY_TYPES: Record<string, { label: string; slug: string; unit: string }> = {
  electricity: { label: 'Electricity', slug: 'electricity', unit: 'kWh' },
  natural_gas: { label: 'Natural Gas', slug: 'natural-gas', unit: 'therm' },
  heating_oil: { label: 'Heating Oil', slug: 'heating-oil', unit: 'gallon' },
  propane: { label: 'Propane', slug: 'propane', unit: 'gallon' },
  water: { label: 'Water', slug: 'water', unit: 'gallon' },
}

/** Convert state name to URL slug: "New York" -> "new-york" */
export function stateToSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-')
}

/** Convert URL slug back to state code: "new-york" -> "NY" */
export function slugToStateCode(slug: string): string | null {
  const lower = slug.toLowerCase().replace(/-/g, ' ')
  for (const [code, name] of Object.entries(US_STATES)) {
    if (name.toLowerCase() === lower) return code
  }
  return null
}

/** Convert utility slug to internal key: "natural-gas" -> "natural_gas" */
export function slugToUtilityKey(slug: string): string | null {
  for (const [key, val] of Object.entries(UTILITY_TYPES)) {
    if (val.slug === slug) return key
  }
  return null
}

/** All state slugs for static generation */
export function allStateSlugs(): string[] {
  return Object.values(US_STATES).map(stateToSlug)
}

/** All utility slugs */
export function allUtilitySlugs(): string[] {
  return Object.values(UTILITY_TYPES).map((u) => u.slug)
}

export const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://rateshift.app'
