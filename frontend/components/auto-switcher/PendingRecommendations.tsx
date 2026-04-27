"use client";

import React from "react";
import {
  ArrowRight,
  CheckCircle2,
  DollarSign,
  TrendingDown,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAgentActivity } from "@/lib/hooks/useAutoSwitcher";
import { formatCurrency } from "./decisionPresentation";

interface PendingRecommendationsProps {
  onApprove: (auditLogId: string) => void;
  isApproving: boolean;
}

/**
 * Renders pending recommendations (decision === "recommend" && !executed).
 *
 * Subscribes to activity directly. The approve mutation is owned by the
 * parent so it can render a global error banner; this component just
 * receives a handler + pending flag.
 */
export default function PendingRecommendations({
  onApprove,
  isApproving,
}: PendingRecommendationsProps) {
  const activityQuery = useAgentActivity();
  const activity = activityQuery.data ?? [];
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
