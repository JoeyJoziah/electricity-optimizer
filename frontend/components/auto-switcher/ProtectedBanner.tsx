"use client";

import React from "react";
import { Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAgentActivity } from "@/lib/hooks/useAutoSwitcher";

interface ProtectedBannerProps {
  onRollback: (executionId: string) => void;
  isRollingBack: boolean;
}

/**
 * Displays a 72-hour rescission protection banner after a recent
 * executed switch, with a rollback CTA.
 *
 * Subscribes to activity directly (the data lives in the React Query
 * cache shared with the rest of the dashboard) but receives the
 * rollback mutation handler from the parent so the parent can render
 * a global error banner if the call fails.
 */
export default function ProtectedBanner({
  onRollback,
  isRollingBack,
}: ProtectedBannerProps) {
  const activityQuery = useAgentActivity();
  const activity = activityQuery.data ?? [];

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
