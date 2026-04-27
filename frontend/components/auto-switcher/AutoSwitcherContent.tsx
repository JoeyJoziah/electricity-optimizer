"use client";

import React, { useCallback, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Header } from "@/components/layout/Header";
import {
  useApproveSwitch,
  useCheckNow,
  useRollback,
} from "@/lib/hooks/useAutoSwitcher";
import type { SwitchDecision } from "@/lib/api/agent-switcher";
import ActivityFeed from "./ActivityFeed";
import AgentStatusCard from "./AgentStatusCard";
import CheckNowResult from "./CheckNowResult";
import CurrentPlanCard from "./CurrentPlanCard";
import PendingRecommendations from "./PendingRecommendations";
import ProtectedBanner from "./ProtectedBanner";

/**
 * Top-level layout shell for the /auto-switcher dashboard.
 *
 * Composition only — every QUERY subscription lives inside the
 * sub-component that uses it (see AgentStatusCard, ActivityFeed,
 * PendingRecommendations, ProtectedBanner). Mutations are hoisted to
 * the shell only so their error banners can render together at the
 * top of the page; mutation handlers are passed down to the children
 * that trigger them.
 *
 * The check-now mutation invalidates only the activity query (the
 * backend writes a new switch_audit_log row and does not modify
 * agent_settings), avoiding the wasteful settings refetch the previous
 * implementation triggered.
 */
export default function AutoSwitcherContent() {
  const [checkResult, setCheckResult] = useState<SwitchDecision | null>(null);

  const checkMutation = useCheckNow();
  const approveMutation = useApproveSwitch();
  const rollbackMutation = useRollback();

  const handleCheckNow = useCallback(() => {
    setCheckResult(null);
    checkMutation.mutate(undefined, {
      onSuccess: (data) => setCheckResult(data),
    });
  }, [checkMutation]);

  const handleApprove = useCallback(
    (auditLogId: string) => approveMutation.mutate(auditLogId),
    [approveMutation],
  );

  const handleRollback = useCallback(
    (executionId: string) => rollbackMutation.mutate(executionId),
    [rollbackMutation],
  );

  const handleDismissResult = useCallback(() => setCheckResult(null), []);

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
          onCheckNow={handleCheckNow}
          isChecking={checkMutation.isPending}
        />

        {/* Check Now Result */}
        {checkResult && (
          <CheckNowResult
            result={checkResult}
            onDismiss={handleDismissResult}
          />
        )}

        {/* Protected Banner (rescission period) */}
        <ProtectedBanner
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
            onApprove={handleApprove}
            isApproving={approveMutation.isPending}
          />
        </div>

        {/* Activity Feed */}
        <ActivityFeed />
      </div>
    </>
  );
}
