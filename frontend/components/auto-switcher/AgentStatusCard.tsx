"use client";

import React from "react";
import { RefreshCw, ToggleLeft, ToggleRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAgentActivity,
  useAgentSettings,
} from "@/lib/hooks/useAutoSwitcher";
import { cn } from "@/lib/utils/cn";
import { formatDate } from "./decisionPresentation";

type StatusVariant = "success" | "warning" | "danger" | "default";

interface AgentStatusCardProps {
  onCheckNow: () => void;
  isChecking: boolean;
}

/**
 * Top-of-page banner showing the agent's enabled/paused/disabled state,
 * the LOA mode (Auto vs Manual), the timestamp of the most recent scan,
 * and the "Check Now" trigger.
 *
 * Owns its own settings + activity subscriptions so it re-renders only
 * when those slices change.
 */
export default function AgentStatusCard({
  onCheckNow,
  isChecking,
}: AgentStatusCardProps) {
  const settingsQuery = useAgentSettings();
  // Activity is needed only to surface the most recent scan timestamp;
  // we read from the same query cache the other dashboard components
  // subscribe to, so this is free after the first fetch.
  const activityQuery = useAgentActivity();

  if (settingsQuery.isLoading) {
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

  const settings = settingsQuery.data;
  const activity = activityQuery.data ?? [];
  const lastScan = activity.length > 0 ? activity[0] : undefined;

  const enabled = settings?.enabled ?? false;
  const paused = !!settings?.paused_until;
  const loaSigned = settings?.loa_signed ?? false;

  let statusLabel = "Disabled";
  let statusVariant: StatusVariant = "default";
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
