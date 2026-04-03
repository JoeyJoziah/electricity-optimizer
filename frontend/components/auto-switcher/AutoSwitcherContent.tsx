"use client";

import React, { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Header } from "@/components/layout/Header";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils/cn";
import {
  getSettings,
  getHistory,
  getActivity,
  checkNow,
  approveSwitch,
  rollback,
} from "@/lib/api/agent-switcher";
import type {
  AgentSettings,
  SwitchAuditEntry,
  SwitchDecision,
  SwitchExecution,
} from "@/lib/api/agent-switcher";
import {
  ToggleLeft,
  ToggleRight,
  Zap,
  Clock,
  DollarSign,
  Shield,
  CheckCircle2,
  XCircle,
  ArrowRight,
  RefreshCw,
  AlertTriangle,
  TrendingDown,
  Eye,
  ThumbsUp,
  X,
  Activity,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

const switcherKeys = {
  settings: ["agent-switcher", "settings"] as const,
  activity: ["agent-switcher", "activity"] as const,
  history: ["agent-switcher", "history"] as const,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(value: number | null | undefined): string {
  if (value == null) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatRate(value: number | null | undefined): string {
  if (value == null) return "--";
  return `$${value.toFixed(4)}/kWh`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString();
}

function formatRelativeTime(iso: string | null | undefined): string {
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

function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

function decisionIcon(decision: string) {
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

function decisionBadge(decision: string): {
  label: string;
  variant: "success" | "info" | "default" | "warning";
} {
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

// ---------------------------------------------------------------------------
// AgentStatusCard
// ---------------------------------------------------------------------------

function AgentStatusCard({
  settings,
  isLoading,
  lastScan,
  onCheckNow,
  isChecking,
}: {
  settings: AgentSettings | undefined;
  isLoading: boolean;
  lastScan: SwitchAuditEntry | undefined;
  onCheckNow: () => void;
  isChecking: boolean;
}) {
  if (isLoading) {
    return (
      <Card variant="bordered" padding="lg">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <Skeleton variant="text" className="h-6 w-48" />
            <Skeleton variant="text" className="h-4 w-64" />
          </div>
          <Skeleton variant="rectangular" className="h-10 w-32" />
        </div>
      </Card>
    );
  }

  const enabled = settings?.enabled ?? false;
  const paused = !!settings?.paused_until;
  const loaSigned = settings?.loa_signed ?? false;

  let statusLabel = "Disabled";
  let statusVariant: "success" | "warning" | "danger" | "default" = "default";
  if (enabled && !paused) {
    statusLabel = loaSigned ? "Active (Auto)" : "Active (Manual)";
    statusVariant = "success";
  } else if (enabled && paused) {
    statusLabel = "Paused";
    statusVariant = "warning";
  } else {
    statusLabel = "Disabled";
    statusVariant = "danger";
  }

  return (
    <Card variant="bordered" padding="lg" data-testid="agent-status-card">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <div
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-xl",
              enabled ? "bg-success-100" : "bg-gray-100",
            )}
          >
            {enabled ? (
              <ToggleRight className="h-6 w-6 text-success-600" />
            ) : (
              <ToggleLeft className="h-6 w-6 text-gray-400" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-gray-900">
                Auto Rate Switcher
              </h2>
              <Badge variant={statusVariant} size="md">
                {statusLabel}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              {lastScan
                ? `Last scan: ${formatDate(lastScan.created_at)}`
                : "No scans yet"}
              {lastScan?.decision && (
                <span className="ml-2">
                  — Result:{" "}
                  <span className="font-medium text-gray-700">
                    {lastScan.decision}
                  </span>
                </span>
              )}
            </p>
            {paused && settings?.paused_until && (
              <p className="mt-1 text-xs text-warning-600">
                Paused until {formatDate(settings.paused_until)}
              </p>
            )}
          </div>
        </div>
        <Button
          variant="primary"
          size="md"
          onClick={onCheckNow}
          loading={isChecking}
          leftIcon={<RefreshCw className="h-4 w-4" />}
          data-testid="check-now-button"
        >
          Check Now
        </Button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// CurrentPlanCard
// ---------------------------------------------------------------------------

function CurrentPlanCard({
  decision,
  isLoading,
}: {
  decision: SwitchDecision | null;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card variant="bordered" padding="lg">
        <CardHeader>
          <Skeleton variant="text" className="h-6 w-40" />
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="flex items-center justify-between">
                <Skeleton variant="text" className="h-4 w-24" />
                <Skeleton variant="text" className="h-4 w-32" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const plan = decision?.current_plan;

  if (!plan) {
    return (
      <Card variant="bordered" padding="lg" data-testid="current-plan-card">
        <CardHeader>
          <CardTitle>Current Plan</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center py-6 text-center">
            <Zap className="h-10 w-10 text-gray-300" />
            <p className="mt-3 text-sm text-gray-500">
              No current plan detected. Run a check to evaluate your rate.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card variant="bordered" padding="lg" data-testid="current-plan-card">
      <CardHeader>
        <CardTitle>Current Plan</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">Plan Name</span>
            <span className="text-sm font-medium text-gray-900">
              {plan.plan_name}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">Provider</span>
            <span className="text-sm font-medium text-gray-900">
              {plan.provider_name}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">Rate</span>
            <span className="text-sm font-semibold text-gray-900">
              {formatRate(plan.rate_kwh)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">Fixed Charge</span>
            <span className="text-sm text-gray-900">
              {formatCurrency(plan.fixed_charge)}/mo
            </span>
          </div>
          {plan.term_months != null && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">Contract Term</span>
              <span className="text-sm text-gray-900">
                {plan.term_months} months
              </span>
            </div>
          )}
          {plan.etf_amount > 0 && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">
                Early Termination Fee
              </span>
              <span className="text-sm font-medium text-danger-600">
                {formatCurrency(plan.etf_amount)}
              </span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// ProtectedBanner
// ---------------------------------------------------------------------------

function ProtectedBanner({
  activity,
  onRollback,
  isRollingBack,
}: {
  activity: SwitchAuditEntry[];
  onRollback: (executionId: string) => void;
  isRollingBack: boolean;
}) {
  // Find most recent executed switch
  const recentSwitch = activity.find(
    (a) => a.decision === "switch" && a.executed,
  );
  if (!recentSwitch) return null;

  // We don't have rescission_ends on audit entries directly, but we can
  // show a general protection banner for recent switches
  const switchDate = new Date(recentSwitch.created_at);
  const now = new Date();
  const hoursSinceSwitch =
    (now.getTime() - switchDate.getTime()) / (1000 * 60 * 60);

  // Show banner for 72 hours (typical rescission window)
  if (hoursSinceSwitch > 72) return null;

  const hoursRemaining = Math.max(0, Math.ceil(72 - hoursSinceSwitch));

  return (
    <Card
      variant="bordered"
      padding="lg"
      className="border-success-200 bg-success-50"
      data-testid="protected-banner"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <Shield className="mt-0.5 h-6 w-6 text-success-600 shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-success-900">
              Your switch is protected
            </h3>
            <p className="mt-1 text-sm text-success-700">
              You switched to{" "}
              <span className="font-medium">
                {recentSwitch.proposed_plan_name ?? "a new plan"}
              </span>
              . You have{" "}
              <span className="font-semibold">{hoursRemaining}h</span> remaining
              in your rescission period to rollback if needed.
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onRollback(recentSwitch.id)}
          loading={isRollingBack}
          className="shrink-0 border-success-300 text-success-700 hover:bg-success-100"
          data-testid="rollback-button"
        >
          Rollback Switch
        </Button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// CheckNowResult
// ---------------------------------------------------------------------------

function CheckNowResult({
  result,
  onDismiss,
}: {
  result: SwitchDecision;
  onDismiss: () => void;
}) {
  const { label, variant } = decisionBadge(result.action);

  return (
    <Card
      variant="bordered"
      padding="lg"
      className="border-primary-200 bg-primary-50"
      data-testid="check-now-result"
    >
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle className="text-primary-900">Evaluation Result</CardTitle>
          <Badge variant={variant} size="md">
            {label}
          </Badge>
        </div>
        <button
          onClick={onDismiss}
          className="rounded-md p-1 text-primary-400 hover:bg-primary-100 hover:text-primary-600 transition-colors"
          aria-label="Dismiss result"
        >
          <X className="h-4 w-4" />
        </button>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-primary-800">{result.reason}</p>

        {result.proposed_plan && (
          <div className="mt-4 rounded-lg bg-white p-4 space-y-2">
            <h4 className="text-sm font-medium text-gray-900">Proposed Plan</h4>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <span className="text-gray-500">Plan</span>
              <span className="text-gray-900">
                {result.proposed_plan.plan_name}
              </span>
              <span className="text-gray-500">Provider</span>
              <span className="text-gray-900">
                {result.proposed_plan.provider_name}
              </span>
              <span className="text-gray-500">Rate</span>
              <span className="font-medium text-gray-900">
                {formatRate(result.proposed_plan.rate_kwh)}
              </span>
            </div>
          </div>
        )}

        {(result.projected_savings_monthly > 0 ||
          result.projected_savings_annual > 0) && (
          <div className="mt-4 flex flex-wrap gap-4">
            <div className="rounded-lg bg-white px-4 py-2">
              <p className="text-xs text-gray-500">Monthly Savings</p>
              <p className="text-lg font-semibold text-success-600">
                {formatCurrency(result.projected_savings_monthly)}
              </p>
            </div>
            <div className="rounded-lg bg-white px-4 py-2">
              <p className="text-xs text-gray-500">Annual Savings</p>
              <p className="text-lg font-semibold text-success-600">
                {formatCurrency(result.projected_savings_annual)}
              </p>
            </div>
            {result.net_savings_year1 > 0 && (
              <div className="rounded-lg bg-white px-4 py-2">
                <p className="text-xs text-gray-500">Net Year 1 (after ETF)</p>
                <p className="text-lg font-semibold text-success-600">
                  {formatCurrency(result.net_savings_year1)}
                </p>
              </div>
            )}
          </div>
        )}

        {result.confidence > 0 && (
          <div className="mt-3 flex items-center gap-2">
            <span className="text-xs text-primary-600">
              Confidence: {Math.round(result.confidence * 100)}%
            </span>
            <div className="h-1.5 flex-1 rounded-full bg-primary-200">
              <div
                className="h-1.5 rounded-full bg-primary-600 transition-all"
                style={{ width: `${Math.min(100, result.confidence * 100)}%` }}
              />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// PendingRecommendations
// ---------------------------------------------------------------------------

function PendingRecommendations({
  activity,
  onApprove,
  isApproving,
}: {
  activity: SwitchAuditEntry[];
  onApprove: (auditLogId: string) => void;
  isApproving: boolean;
}) {
  const pending = activity.filter(
    (a) => a.decision === "recommend" && !a.executed,
  );

  if (pending.length === 0) return null;

  return (
    <Card variant="bordered" padding="lg" data-testid="pending-recommendations">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>Pending Recommendations</CardTitle>
          <Badge variant="info" size="sm">
            {pending.length}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {pending.map((rec) => (
            <div
              key={rec.id}
              className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4 sm:flex-row sm:items-center sm:justify-between"
              data-testid="recommendation-card"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <TrendingDown className="h-4 w-4 text-success-500 shrink-0" />
                  <span className="text-sm font-medium text-gray-900 truncate">
                    {rec.current_plan_name ?? "Current plan"}
                    <ArrowRight className="mx-1.5 inline h-3 w-3 text-gray-400" />
                    {rec.proposed_plan_name ?? "Recommended plan"}
                  </span>
                </div>
                <p className="mt-1 text-sm text-gray-500 line-clamp-2">
                  {rec.reason}
                </p>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-500">
                  {rec.savings_monthly != null && (
                    <span className="flex items-center gap-1">
                      <DollarSign className="h-3 w-3" />
                      {formatCurrency(rec.savings_monthly)}/mo
                    </span>
                  )}
                  {rec.savings_annual != null && (
                    <span className="flex items-center gap-1">
                      <DollarSign className="h-3 w-3" />
                      {formatCurrency(rec.savings_annual)}/yr
                    </span>
                  )}
                  {rec.confidence_score != null && (
                    <span>
                      Confidence: {Math.round(rec.confidence_score * 100)}%
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => onApprove(rec.id)}
                  loading={isApproving}
                  leftIcon={<CheckCircle2 className="h-4 w-4" />}
                  data-testid="approve-button"
                >
                  Approve
                </Button>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// ActivityFeed
// ---------------------------------------------------------------------------

function ActivityFeed({
  activity,
  isLoading,
}: {
  activity: SwitchAuditEntry[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card variant="bordered" padding="lg">
        <CardHeader>
          <Skeleton variant="text" className="h-6 w-36" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="flex gap-3">
                <Skeleton variant="circular" className="h-8 w-8 shrink-0" />
                <div className="flex-1 space-y-1">
                  <Skeleton variant="text" className="h-4 w-3/4" />
                  <Skeleton variant="text" className="h-3 w-1/2" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (activity.length === 0) {
    return (
      <Card variant="bordered" padding="lg" data-testid="activity-feed">
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center py-8 text-center">
            <Clock className="h-10 w-10 text-gray-300" />
            <p className="mt-3 text-sm text-gray-500">
              No activity yet. Run your first check to see results here.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card variant="bordered" padding="lg" data-testid="activity-feed">
      <CardHeader>
        <CardTitle>Recent Activity</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="relative">
          {/* Timeline line */}
          <div
            className="absolute left-4 top-0 bottom-0 w-px bg-gray-200"
            aria-hidden="true"
          />

          <div className="space-y-4">
            {activity.map((entry, idx) => {
              const badge = decisionBadge(entry.decision);
              return (
                <div
                  key={entry.id}
                  className="relative flex gap-4 pl-10"
                  data-testid="activity-entry"
                >
                  {/* Timeline dot */}
                  <div
                    className="absolute left-2 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-white ring-2 ring-gray-200"
                    aria-hidden="true"
                  >
                    {decisionIcon(entry.decision)}
                  </div>

                  <div className="min-w-0 flex-1 rounded-lg border border-gray-100 bg-white p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={badge.variant} size="sm">
                        {badge.label}
                      </Badge>
                      {entry.executed && (
                        <Badge variant="success" size="sm">
                          Executed
                        </Badge>
                      )}
                      <span className="ml-auto text-xs text-gray-400">
                        {formatDate(entry.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-gray-700 line-clamp-2">
                      {entry.reason}
                    </p>
                    {(entry.current_plan_name || entry.proposed_plan_name) && (
                      <p className="mt-1 text-xs text-gray-500">
                        {entry.current_plan_name && (
                          <span>{entry.current_plan_name}</span>
                        )}
                        {entry.current_plan_name &&
                          entry.proposed_plan_name && (
                            <ArrowRight className="mx-1 inline h-3 w-3 text-gray-400" />
                          )}
                        {entry.proposed_plan_name && (
                          <span className="font-medium">
                            {entry.proposed_plan_name}
                          </span>
                        )}
                      </p>
                    )}
                    {entry.savings_monthly != null &&
                      entry.savings_monthly > 0 && (
                        <p className="mt-1 text-xs text-success-600">
                          Savings: {formatCurrency(entry.savings_monthly)}/mo
                          {entry.savings_annual != null &&
                            ` (${formatCurrency(entry.savings_annual)}/yr)`}
                        </p>
                      )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main AutoSwitcherContent
// ---------------------------------------------------------------------------

export default function AutoSwitcherContent() {
  const queryClient = useQueryClient();
  const [checkResult, setCheckResult] = useState<SwitchDecision | null>(null);

  // ----- Queries -----
  const settingsQuery = useQuery({
    queryKey: switcherKeys.settings,
    queryFn: ({ signal }) => getSettings(signal),
    staleTime: 30_000,
  });

  const activityQuery = useQuery({
    queryKey: switcherKeys.activity,
    queryFn: ({ signal }) => getActivity(10, signal),
    staleTime: 60_000,
  });

  // ----- Mutations -----
  const checkMutation = useMutation({
    mutationFn: () => checkNow(),
    onSuccess: (data) => {
      setCheckResult(data);
      queryClient.invalidateQueries({ queryKey: switcherKeys.activity });
      queryClient.invalidateQueries({ queryKey: switcherKeys.settings });
    },
  });

  const approveMutation = useMutation({
    mutationFn: (auditLogId: string) => approveSwitch(auditLogId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: switcherKeys.activity });
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: (executionId: string) => rollback(executionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: switcherKeys.activity });
    },
  });

  const handleCheckNow = useCallback(() => {
    setCheckResult(null);
    checkMutation.mutate();
  }, [checkMutation]);

  const handleApprove = useCallback(
    (auditLogId: string) => approveMutation.mutate(auditLogId),
    [approveMutation],
  );

  const handleRollback = useCallback(
    (executionId: string) => rollbackMutation.mutate(executionId),
    [rollbackMutation],
  );

  const activity = activityQuery.data ?? [];
  const lastScan = activity.length > 0 ? activity[0] : undefined;

  return (
    <>
      <Header title="Auto Switcher" />
      <div className="p-4 lg:p-6 space-y-6">
        {/* Error banners */}
        {checkMutation.isError && (
          <div
            className="flex items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3"
            role="alert"
          >
            <AlertTriangle className="h-5 w-5 text-danger-500 shrink-0" />
            <p className="text-sm text-danger-700">
              Failed to run evaluation. Please try again.
            </p>
          </div>
        )}
        {approveMutation.isError && (
          <div
            className="flex items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3"
            role="alert"
          >
            <AlertTriangle className="h-5 w-5 text-danger-500 shrink-0" />
            <p className="text-sm text-danger-700">
              Failed to approve recommendation. Please try again.
            </p>
          </div>
        )}
        {rollbackMutation.isError && (
          <div
            className="flex items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3"
            role="alert"
          >
            <AlertTriangle className="h-5 w-5 text-danger-500 shrink-0" />
            <p className="text-sm text-danger-700">
              Failed to rollback switch. Please try again.
            </p>
          </div>
        )}

        {/* Agent Status Banner */}
        <AgentStatusCard
          settings={settingsQuery.data}
          isLoading={settingsQuery.isLoading}
          lastScan={lastScan}
          onCheckNow={handleCheckNow}
          isChecking={checkMutation.isPending}
        />

        {/* Check Now Result */}
        {checkResult && (
          <CheckNowResult
            result={checkResult}
            onDismiss={() => setCheckResult(null)}
          />
        )}

        {/* Protected Banner (rescission period) */}
        <ProtectedBanner
          activity={activity}
          onRollback={handleRollback}
          isRollingBack={rollbackMutation.isPending}
        />

        {/* Main content grid */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Current Plan */}
          <CurrentPlanCard
            decision={checkResult}
            isLoading={checkMutation.isPending && !checkResult}
          />

          {/* Pending Recommendations */}
          <PendingRecommendations
            activity={activity}
            onApprove={handleApprove}
            isApproving={approveMutation.isPending}
          />
        </div>

        {/* Activity Feed */}
        <ActivityFeed activity={activity} isLoading={activityQuery.isLoading} />
      </div>
    </>
  );
}
