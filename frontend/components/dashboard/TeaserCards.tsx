import React from "react";
import Link from "next/link";
import { ArrowRight, TrendingUp, DollarSign } from "lucide-react";
import { US_REGIONS } from "@/lib/constants/regions";

// ---------------------------------------------------------------------------
// Region-based savings estimate ranges (annual, in USD)
// ---------------------------------------------------------------------------

interface SavingsRange {
  low: number;
  high: number;
}

const REGION_SAVINGS_RANGES: Record<string, SavingsRange> = {
  Northeast: { low: 200, high: 400 },
  Southeast: { low: 150, high: 300 },
  Midwest: { low: 160, high: 320 },
  "South Central": { low: 150, high: 300 },
  West: { low: 180, high: 350 },
  International: { low: 150, high: 350 },
};

const DEFAULT_SAVINGS_RANGE: SavingsRange = { low: 150, high: 350 };

/**
 * Map a region value (e.g. "us_ct") to the census region group label
 * (e.g. "Northeast") by looking it up in US_REGIONS.
 */
function getRegionGroupLabel(region: string | undefined): string | null {
  if (!region) return null;
  for (const group of US_REGIONS) {
    if (group.states.some((s) => s.value === region)) {
      return group.label;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Placeholder forecast data points for the teaser chart shape
// ---------------------------------------------------------------------------

const PLACEHOLDER_HOURS = [
  "12am",
  "3am",
  "6am",
  "9am",
  "12pm",
  "3pm",
  "6pm",
  "9pm",
  "12am",
];

/** SVG path points for a realistic-looking price curve shape */
const PLACEHOLDER_PATH =
  "M 0 70 C 30 65, 50 40, 80 35 C 110 30, 140 25, 170 20 C 200 15, 220 30, 250 45 C 280 60, 310 75, 340 80 C 370 85, 400 70, 420 55 C 440 40, 460 50, 480 60";
const PLACEHOLDER_AREA = `${PLACEHOLDER_PATH} L 480 100 L 0 100 Z`;

// ---------------------------------------------------------------------------
// ForecastTeaser
// ---------------------------------------------------------------------------

/**
 * A teaser version of the 24-hour forecast chart for free-tier users.
 *
 * Shows the chart SHAPE with visible time axis labels but blurs the actual
 * price values. An overlay CTA invites upgrade for full access.
 *
 * The user can see that forecast data EXISTS and looks useful — the "aha
 * moment" comes before the paywall.
 */
export function ForecastTeaser() {
  return (
    <div data-testid="forecast-teaser-chart" className="relative">
      {/* Blurred data layer — shows chart shape without readable values */}
      <div
        data-testid="forecast-teaser-blurred-data"
        aria-label="Forecast chart preview — upgrade to Pro for exact values"
        style={{ filter: "blur(8px)" }}
        className="pointer-events-none select-none"
      >
        <svg
          viewBox="0 0 480 120"
          className="h-48 w-full"
          preserveAspectRatio="none"
          role="img"
          aria-hidden="true"
        >
          {/* Grid lines */}
          <line
            x1="0"
            y1="25"
            x2="480"
            y2="25"
            stroke="#e5e7eb"
            strokeDasharray="4 4"
          />
          <line
            x1="0"
            y1="50"
            x2="480"
            y2="50"
            stroke="#e5e7eb"
            strokeDasharray="4 4"
          />
          <line
            x1="0"
            y1="75"
            x2="480"
            y2="75"
            stroke="#e5e7eb"
            strokeDasharray="4 4"
          />

          {/* Confidence band area */}
          <path
            d="M 0 60 C 30 55, 50 30, 80 25 C 110 20, 140 15, 170 10 C 200 5, 220 20, 250 35 C 280 50, 310 65, 340 70 C 370 75, 400 60, 420 45 C 440 30, 460 40, 480 50 L 480 100 L 0 100 Z"
            fill="#f59e0b"
            fillOpacity="0.15"
          />

          {/* Forecast area fill */}
          <path d={PLACEHOLDER_AREA} fill="#f59e0b" fillOpacity="0.25" />

          {/* Forecast line */}
          <path
            d={PLACEHOLDER_PATH}
            stroke="#f59e0b"
            strokeWidth="2.5"
            fill="none"
          />

          {/* Y-axis price labels (blurred) */}
          <text x="4" y="22" fontSize="10" fill="#6b7280">
            $0.30
          </text>
          <text x="4" y="47" fontSize="10" fill="#6b7280">
            $0.25
          </text>
          <text x="4" y="72" fontSize="10" fill="#6b7280">
            $0.20
          </text>
          <text x="4" y="97" fontSize="10" fill="#6b7280">
            $0.15
          </text>
        </svg>
      </div>

      {/* Time axis labels — visible (not blurred) */}
      <div
        data-testid="forecast-teaser-time-axis"
        className="flex justify-between px-1 text-xs text-gray-400"
        aria-hidden="true"
      >
        {PLACEHOLDER_HOURS.map((label, idx) => (
          <span key={`${idx}-${label}`}>{label}</span>
        ))}
      </div>

      {/* Overlay CTA — positioned below the chart, not replacing it */}
      <div
        data-testid="forecast-teaser-cta"
        className="mt-3 flex flex-col items-center text-center"
      >
        <div className="mb-2 flex items-center gap-1.5 text-sm text-gray-500">
          <TrendingUp className="h-4 w-4 text-primary-500" />
          <span>Upgrade to see exact forecasts</span>
        </div>
        <Link
          href="/pricing"
          className="inline-flex items-center gap-1.5 rounded-lg border border-primary-300 bg-white px-4 py-2 text-sm font-medium text-primary-700 transition-colors hover:bg-primary-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        >
          Unlock Forecasts
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SavingsTeaser
// ---------------------------------------------------------------------------

export interface SavingsTeaserProps {
  /** User's region (e.g. "us_ct"). Used to determine savings estimate range. */
  region: string | undefined;
}

/**
 * A teaser savings card for free-tier users.
 *
 * Shows an estimated savings range based on the user's region instead of a
 * locked gate. The "aha moment" (potential savings) comes before the paywall.
 */
export function SavingsTeaser({ region }: SavingsTeaserProps) {
  const groupLabel = getRegionGroupLabel(region);
  const range = groupLabel
    ? (REGION_SAVINGS_RANGES[groupLabel] ?? DEFAULT_SAVINGS_RANGE)
    : DEFAULT_SAVINGS_RANGE;

  return (
    <div className="flex flex-col items-center px-4 py-6 text-center">
      {/* Icon */}
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-success-50">
        <DollarSign className="h-5 w-5 text-success-600" />
      </div>

      {/* Heading */}
      <p className="text-sm font-medium text-gray-500">
        Estimated Annual Savings
      </p>

      {/* Range — prominent, green, visible */}
      <p
        data-testid="savings-teaser-range"
        aria-label={`Estimated annual savings between $${range.low} and $${range.high} per year based on your region`}
        className="mt-2 text-2xl font-bold text-success-700"
      >
        ${range.low}&ndash;${range.high}
        <span className="ml-1 text-base font-medium text-success-600">
          /year
        </span>
      </p>

      {/* Region context */}
      {groupLabel && (
        <p className="mt-1 text-xs text-gray-400">
          Based on {groupLabel} region averages
        </p>
      )}

      {/* CTA — below the value, subtle */}
      <div data-testid="savings-teaser-cta" className="mt-4">
        <p className="mb-2 text-sm text-gray-500">Get exact savings with Pro</p>
        <Link
          href="/pricing"
          className="inline-flex items-center gap-1.5 rounded-lg border border-primary-300 bg-white px-4 py-2 text-sm font-medium text-primary-700 transition-colors hover:bg-primary-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        >
          See Exact Savings
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}
