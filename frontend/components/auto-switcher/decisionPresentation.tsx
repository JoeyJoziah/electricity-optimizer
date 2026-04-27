/**
 * Pure presentation helpers shared across Auto Switcher sub-components.
 *
 * These have no side effects and no data dependencies, so each sub-component
 * can import only what it uses without pulling in unrelated modules.
 */

import { Activity, Eye, ThumbsUp, Zap } from "lucide-react";

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatRate(value: number | null | undefined): string {
  if (value == null) return "--";
  return `$${value.toFixed(4)}/kWh`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString();
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "--";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "Expired";
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  if (hours > 24) {
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h remaining`;
  }
  if (hours > 0) return `${hours}h ${minutes}m remaining`;
  return `${minutes}m remaining`;
}

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

// ---------------------------------------------------------------------------
// Decision presentation
// ---------------------------------------------------------------------------

export type DecisionBadgeVariant = "success" | "info" | "default" | "warning";

export interface DecisionBadgeMeta {
  label: string;
  variant: DecisionBadgeVariant;
}

export function decisionIcon(decision: string) {
  switch (decision) {
    case "switch":
      return <Zap className="h-4 w-4 text-success-600" />;
    case "recommend":
      return <ThumbsUp className="h-4 w-4 text-primary-600" />;
    case "hold":
      return <Eye className="h-4 w-4 text-gray-500" />;
    case "monitor":
      return <Activity className="h-4 w-4 text-warning-600" />;
    default:
      return <Eye className="h-4 w-4 text-gray-400" />;
  }
}

export function decisionBadge(decision: string): DecisionBadgeMeta {
  switch (decision) {
    case "switch":
      return { label: "Switched", variant: "success" };
    case "recommend":
      return { label: "Recommendation", variant: "info" };
    case "hold":
      return { label: "Hold", variant: "default" };
    case "monitor":
      return { label: "Monitoring", variant: "warning" };
    default:
      return { label: decision, variant: "default" };
  }
}
