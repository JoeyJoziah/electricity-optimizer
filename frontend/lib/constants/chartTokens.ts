/**
 * Chart design tokens backed by CSS custom properties from globals.css.
 *
 * All chart components should import colors and styles from here instead of
 * hardcoding hex values. This enables theming by overriding the CSS variables
 * in :root (e.g. for dark mode or branded instances).
 *
 * The CSS variables are defined in frontend/app/globals.css under :root.
 */

/**
 * Ordered chart palette referencing --chart-1 through --chart-6.
 * Used by SavingsDonut (Cell fills), any categorical series, etc.
 */
export const CHART_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)',
] as const

/** Semantic chart color aliases for self-documenting usage in specific charts. */
export const chartColor = {
  /** Primary data series (actual prices, main line) */
  primary: 'var(--chart-1)',
  /** Success / savings / optimal periods */
  success: 'var(--chart-2)',
  /** Warning / forecast line */
  warning: 'var(--chart-3)',
  /** Danger / alerts */
  danger: 'var(--chart-4)',
  /** Purple — auxiliary series */
  purple: 'var(--chart-5)',
  /** Cyan — auxiliary series */
  cyan: 'var(--chart-6)',

  /** Grid lines */
  grid: 'var(--chart-grid)',
  /** Axis labels */
  axis: 'var(--chart-axis)',
  /** Forecast confidence band */
  confidence: 'var(--chart-confidence)',

  /** Tooltip background */
  tooltipBg: 'var(--chart-tooltip-bg)',
  /** Tooltip border */
  tooltipBorder: 'var(--chart-tooltip-border)',
} as const

/** Shared Recharts Tooltip contentStyle referencing CSS custom properties. */
export const chartTooltipStyle: React.CSSProperties = {
  backgroundColor: chartColor.tooltipBg,
  border: `1px solid ${chartColor.tooltipBorder}`,
  borderRadius: '8px',
}

/** Tooltip style with shadow (used by PriceLineChart). */
export const chartTooltipStyleWithShadow: React.CSSProperties = {
  ...chartTooltipStyle,
  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
}

// React import needed for CSSProperties type above
import type React from 'react'
