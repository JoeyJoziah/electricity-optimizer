"use client";

import React, { useState, useCallback } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Header } from "@/components/layout/Header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/utils/cn";
import { getHistory, rollback } from "@/lib/api/agent-switcher";
import type { SwitchAuditEntry } from "@/lib/api/agent-switcher";
import {
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Clock,
  History,
  RotateCcw,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Loader2,
  ArrowLeft,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;
const ROLLBACK_WINDOW_DAYS = 30;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Derive a display status from the SwitchAuditEntry.
 *
 * The audit entry has `decision` (switch/recommend/hold/monitor) and
 * `executed` boolean. We map these to human-readable statuses.
 */
function deriveStatus(entry: SwitchAuditEntry): string {
  if (entry.decision === "switch" && entry.executed) return "active";
  if (entry.decision === "switch" && !entry.executed) return "initiated";
  if (entry.decision === "recommend") return "recommended";
  if (entry.decision === "hold") return "hold";
  if (entry.decision === "monitor") return "monitoring";
  return entry.decision;
}

type StatusVariant = "success" | "warning" | "danger" | "default" | "info";

function statusConfig(status: string): {
  label: string;
  variant: StatusVariant;
} {
  switch (status) {
    case "active":
      return { label: "Active", variant: "success" };
    case "initiated":
    case "submitted":
    case "accepted":
      return {
        label: status.charAt(0).toUpperCase() + status.slice(1),
        variant: "warning",
      };
    case "recommended":
      return { label: "Recommended", variant: "info" };
    case "failed":
      return { label: "Failed", variant: "danger" };
    case "rolled_back":
      return { label: "Rolled Back", variant: "default" };
    case "hold":
      return { label: "Hold", variant: "default" };
    case "monitoring":
      return { label: "Monitoring", variant: "info" };
    default:
      return { label: status, variant: "default" };
  }
}

function statusIcon(status: string) {
  switch (status) {
    case "active":
      return <CheckCircle2 className="h-4 w-4 text-success-600" />;
    case "initiated":
    case "submitted":
    case "accepted":
    case "recommended":
      return <Clock className="h-4 w-4 text-warning-600" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-danger-600" />;
    case "rolled_back":
      return <RotateCcw className="h-4 w-4 text-gray-400" />;
    default:
      return <Clock className="h-4 w-4 text-gray-400" />;
  }
}

function isWithinRollbackWindow(createdAt: string): boolean {
  const created = new Date(createdAt);
  const now = new Date();
  const diffMs = now.getTime() - created.getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  return diffDays <= ROLLBACK_WINDOW_DAYS;
}

function triggerTypeLabel(trigger: string): string {
  switch (trigger) {
    case "scheduled":
      return "Scheduled Check";
    case "manual":
      return "Manual Check";
    case "price_change":
      return "Price Change Detected";
    case "contract_expiry":
      return "Contract Expiring";
    default:
      return trigger
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

// ---------------------------------------------------------------------------
// DecisionReasoning — expandable detail section
// ---------------------------------------------------------------------------

function DecisionReasoning({ entry }: { entry: SwitchAuditEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors"
        aria-expanded={expanded}
        aria-label={
          expanded ? "Collapse decision details" : "Expand decision details"
        }
      >
        {expanded ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
        Decision Details
      </button>

      {expanded && (
        <div className="mt-3 space-y-2 text-sm">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>
              <span className="text-xs font-medium text-gray-500">Trigger</span>
              <p className="text-gray-900">
                {triggerTypeLabel(entry.trigger_type)}
              </p>
            </div>
            {entry.confidence_score !== null && (
              <div>
                <span className="text-xs font-medium text-gray-500">
                  Confidence
                </span>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-gray-200">
                    <div
                      className={cn(
                        "h-1.5 rounded-full",
                        (entry.confidence_score ?? 0) >= 0.8
                          ? "bg-success-500"
                          : (entry.confidence_score ?? 0) >= 0.5
                            ? "bg-warning-500"
                            : "bg-danger-500",
                      )}
                      style={{
                        width: `${(entry.confidence_score ?? 0) * 100}%`,
                      }}
                    />
                  </div>
                  <span className="text-xs text-gray-600">
                    {Math.round((entry.confidence_score ?? 0) * 100)}%
                  </span>
                </div>
              </div>
            )}
          </div>

          {entry.tier && (
            <div>
              <span className="text-xs font-medium text-gray-500">Tier</span>
              <p className="text-gray-900 capitalize">{entry.tier}</p>
            </div>
          )}

          {entry.reason && (
            <div>
              <span className="text-xs font-medium text-gray-500">
                Reasoning
              </span>
              <p className="text-gray-700 leading-relaxed">{entry.reason}</p>
            </div>
          )}

          {entry.etf_cost > 0 && (
            <div className="rounded-lg bg-warning-50 p-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-warning-600" />
                <span className="text-xs font-medium text-warning-800">
                  Early Termination Fee
                </span>
              </div>
              <p className="mt-1 text-sm text-warning-700">
                {formatCurrency(entry.etf_cost)} ETF applied.
                {entry.net_savings_year1 !== null && (
                  <>
                    {" "}
                    Net savings after ETF:{" "}
                    {formatCurrency(entry.net_savings_year1)}/year
                  </>
                )}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RollbackButton — only visible for active switches within 30 days
// ---------------------------------------------------------------------------

function RollbackButton({ entry }: { entry: SwitchAuditEntry }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const queryClient = useQueryClient();

  const rollbackMutation = useMutation({
    mutationFn: () => rollback(entry.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auto-switcher", "history"] });
    },
  });

  const status = deriveStatus(entry);
  const canRollback =
    status === "active" && isWithinRollbackWindow(entry.created_at);

  if (!canRollback) return null;

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setShowConfirm(true)}
        disabled={rollbackMutation.isPending}
        leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
        aria-label={`Rollback switch from ${entry.current_plan_name ?? "unknown"} to ${entry.proposed_plan_name ?? "unknown"}`}
      >
        {rollbackMutation.isPending ? "Rolling back..." : "Rollback"}
      </Button>

      <Modal
        open={showConfirm}
        onClose={() => setShowConfirm(false)}
        title="Confirm Rollback"
        description={`This will reverse the switch from "${entry.current_plan_name ?? "previous plan"}" to "${entry.proposed_plan_name ?? "new plan"}". You will be returned to your previous rate plan.`}
        confirmLabel="Rollback Switch"
        cancelLabel="Keep Current"
        onConfirm={() => rollbackMutation.mutate()}
        variant="danger"
      />

      {rollbackMutation.isError && (
        <p className="mt-1 text-xs text-danger-600" role="alert">
          Rollback failed. Please try again or contact support.
        </p>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// SwitchCard — single timeline entry
// ---------------------------------------------------------------------------

function SwitchCard({ entry }: { entry: SwitchAuditEntry }) {
  const status = deriveStatus(entry);
  const config = statusConfig(status);

  return (
    <Card variant="bordered" padding="none" className="overflow-hidden">
      <div className="p-4 sm:p-5">
        {/* Top row: date + status */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            {statusIcon(status)}
            <time dateTime={entry.created_at}>
              {formatDateTime(entry.created_at)}
            </time>
          </div>
          <Badge variant={config.variant} size="sm">
            {config.label}
          </Badge>
        </div>

        {/* Plan transition */}
        <div className="mt-3">
          {entry.current_plan_name || entry.proposed_plan_name ? (
            <div className="flex flex-wrap items-center gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {entry.current_plan_name ?? "Unknown Plan"}
                </p>
              </div>
              <ArrowRight
                className="h-4 w-4 flex-shrink-0 text-gray-400"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-sm font-medium text-primary-700 truncate">
                  {entry.proposed_plan_name ?? "Unknown Plan"}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">
              {entry.decision === "hold"
                ? "Current plan evaluated -- no switch recommended"
                : entry.decision === "monitor"
                  ? "Rate monitoring in progress"
                  : "Plan details unavailable"}
            </p>
          )}
        </div>

        {/* Savings */}
        {(entry.savings_monthly !== null || entry.savings_annual !== null) && (
          <div className="mt-3 flex flex-wrap items-center gap-4">
            {entry.savings_monthly !== null && (
              <div className="flex items-center gap-1.5">
                <TrendingUp className="h-4 w-4 text-success-600" />
                <span className="text-sm font-semibold text-success-700">
                  {formatCurrency(entry.savings_monthly)}/mo
                </span>
              </div>
            )}
            {entry.savings_annual !== null && (
              <span className="text-sm text-gray-500">
                {formatCurrency(entry.savings_annual)}/year
              </span>
            )}
          </div>
        )}

        {/* Decision reasoning (expandable) */}
        <DecisionReasoning entry={entry} />

        {/* Rollback button */}
        <div className="mt-3">
          <RollbackButton entry={entry} />
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// SwitchTimeline — vertical timeline layout
// ---------------------------------------------------------------------------

function SwitchTimeline({ entries }: { entries: SwitchAuditEntry[] }) {
  return (
    <div className="relative">
      {/* Vertical timeline line */}
      <div
        className="absolute left-4 top-0 bottom-0 w-px bg-gray-200 sm:left-5"
        aria-hidden="true"
      />

      <div className="space-y-4">
        {entries.map((entry, index) => (
          <div key={entry.id} className="relative pl-10 sm:pl-12">
            {/* Timeline dot */}
            <div
              className={cn(
                "absolute left-2.5 top-5 h-3 w-3 rounded-full border-2 border-white sm:left-3.5",
                deriveStatus(entry) === "active"
                  ? "bg-success-500"
                  : deriveStatus(entry) === "failed"
                    ? "bg-danger-500"
                    : deriveStatus(entry) === "rolled_back"
                      ? "bg-gray-400"
                      : "bg-primary-500",
              )}
              aria-hidden="true"
            />

            {/* Date group separator */}
            {(index === 0 ||
              formatDate(entry.created_at) !==
                formatDate(entries[index - 1].created_at)) && (
              <p className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-400">
                {formatDate(entry.created_at)}
              </p>
            )}

            <SwitchCard entry={entry} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div
      className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center"
      data-testid="empty-history"
    >
      <History className="mx-auto h-12 w-12 text-gray-300" />
      <h3 className="mt-4 text-sm font-medium text-gray-900">
        No switch history yet
      </h3>
      <p className="mt-1 text-sm text-gray-500">
        When the Auto Switcher evaluates your rates, the decisions and switches
        will appear here.
      </p>
      <Link
        href="/auto-switcher/settings"
        className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:text-primary-700 transition-colors"
      >
        Configure Auto Switcher
        <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading state (inline, for additional pages)
// ---------------------------------------------------------------------------

function InlineLoadingSkeleton() {
  return (
    <div className="space-y-4 pl-10 sm:pl-12">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-gray-200 bg-white p-5 space-y-3"
        >
          <div className="flex items-center justify-between">
            <Skeleton variant="text" className="h-4 w-32" />
            <Skeleton variant="text" className="h-5 w-16 rounded-full" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton variant="text" className="h-5 w-28" />
            <Skeleton variant="text" className="h-4 w-4" />
            <Skeleton variant="text" className="h-5 w-28" />
          </div>
          <Skeleton variant="text" className="h-4 w-24" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error state (inline)
// ---------------------------------------------------------------------------

function InlineError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-danger-200 bg-danger-50 p-6 text-center">
      <p className="text-sm text-danger-700">
        Failed to load switch history. Please try again.
      </p>
      <Button onClick={onRetry} size="sm" className="mt-3">
        Retry
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SwitchHistoryContent() {
  const [offset, setOffset] = useState(0);
  const [allEntries, setAllEntries] = useState<SwitchAuditEntry[]>([]);

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["auto-switcher", "history", offset],
    queryFn: ({ signal }) => getHistory(PAGE_SIZE, offset, signal),
    staleTime: 60_000,
  });

  // Merge fetched entries into accumulated list when data changes
  React.useEffect(() => {
    if (data && data.length > 0) {
      setAllEntries((prev) => {
        const existingIds = new Set(prev.map((e) => e.id));
        const newEntries = data.filter((e) => !existingIds.has(e.id));
        return [...prev, ...newEntries];
      });
    }
  }, [data]);

  const hasMore = data?.length === PAGE_SIZE;

  const handleLoadMore = useCallback(() => {
    setOffset((prev) => prev + PAGE_SIZE);
  }, []);

  const isInitialLoad = isLoading && offset === 0;
  const isLoadingMore = isFetching && offset > 0;

  return (
    <>
      <Header title="Switch History" />
      <div className="p-4 lg:p-6">
        {/* Back link + page description */}
        <div className="mb-6">
          <Link
            href="/auto-switcher/settings"
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors mb-3"
          >
            <ArrowLeft className="h-4 w-4" />
            Auto Switcher Settings
          </Link>
          <p className="text-sm text-gray-500">
            A timeline of every rate evaluation and switch decision made by the
            Auto Switcher agent.
          </p>
        </div>

        {/* Content states */}
        {isInitialLoad ? (
          <InlineLoadingSkeleton />
        ) : isError && allEntries.length === 0 ? (
          <InlineError onRetry={() => refetch()} />
        ) : allEntries.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            <SwitchTimeline entries={allEntries} />

            {/* Load More */}
            <div className="mt-6 flex justify-center">
              {hasMore ? (
                <Button
                  variant="outline"
                  onClick={handleLoadMore}
                  loading={isLoadingMore}
                  disabled={isLoadingMore}
                >
                  {isLoadingMore ? "Loading..." : "Load More"}
                </Button>
              ) : (
                allEntries.length > PAGE_SIZE && (
                  <p className="text-sm text-gray-400">
                    All {allEntries.length} entries loaded
                  </p>
                )
              )}
            </div>

            {/* Load-more error */}
            {isError && allEntries.length > 0 && (
              <div className="mt-4 text-center">
                <p className="text-xs text-danger-600">
                  Failed to load more entries.
                </p>
                <button
                  onClick={() => refetch()}
                  className="mt-1 text-xs font-medium text-primary-600 hover:text-primary-700"
                >
                  Retry
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
