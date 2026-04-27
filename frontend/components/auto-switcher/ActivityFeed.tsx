"use client";

import React from "react";
import { ArrowRight, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgentActivity } from "@/lib/hooks/useAutoSwitcher";
import {
  decisionBadge,
  decisionIcon,
  formatCurrency,
  formatDate,
} from "./decisionPresentation";

/**
 * Timeline of recent agent activity entries.
 * Owns its own activity subscription so it re-renders only when
 * activity changes; settings/check-result changes do not affect it.
 */
export default function ActivityFeed() {
  const activityQuery = useAgentActivity();

  if (activityQuery.isLoading) {
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

  const activity = activityQuery.data ?? [];

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
            {activity.map((entry) => {
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
