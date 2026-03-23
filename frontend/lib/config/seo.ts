/**
 * SEO constants for programmatic rate pages.
 */

import { US_STATES } from "@/lib/constants/regions";

// Re-export for consumers that import US_STATES from this module
export { US_STATES };

export const UTILITY_TYPES: Record<
  string,
  { label: string; slug: string; unit: string }
> = {
  electricity: { label: "Electricity", slug: "electricity", unit: "kWh" },
  natural_gas: { label: "Natural Gas", slug: "natural-gas", unit: "therm" },
  heating_oil: { label: "Heating Oil", slug: "heating-oil", unit: "gallon" },
  propane: { label: "Propane", slug: "propane", unit: "gallon" },
  water: { label: "Water", slug: "water", unit: "gallon" },
};

/** Convert state name to URL slug: "New York" -> "new-york" */
export function stateToSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, "-");
}

/** Convert URL slug back to state code: "new-york" -> "NY" */
export function slugToStateCode(slug: string): string | null {
  const lower = slug.toLowerCase().replace(/-/g, " ");
  for (const [code, name] of Object.entries(US_STATES)) {
    if (name.toLowerCase() === lower) return code;
  }
  return null;
}

/** Convert utility slug to internal key: "natural-gas" -> "natural_gas" */
export function slugToUtilityKey(slug: string): string | null {
  for (const [key, val] of Object.entries(UTILITY_TYPES)) {
    if (val.slug === slug) return key;
  }
  return null;
}

/** All state slugs for static generation */
export function allStateSlugs(): string[] {
  return Object.values(US_STATES).map(stateToSlug);
}

/** All utility slugs */
export function allUtilitySlugs(): string[] {
  return Object.values(UTILITY_TYPES).map((u) => u.slug);
}

export const BASE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://rateshift.app";
