"use client";

import React from "react";
import { Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { SwitchDecision } from "@/lib/api/agent-switcher";
import { formatCurrency, formatRate } from "./decisionPresentation";

interface CurrentPlanCardProps {
  decision: SwitchDecision | null;
  isLoading: boolean;
}

/**
 * Renders the user's current plan derived from the latest decision result.
 * Receives the decision via prop because that data lives in the parent's
 * local UI state (the in-flight check result), not in the React Query cache.
 */
export default function CurrentPlanCard({
  decision,
  isLoading,
}: CurrentPlanCardProps) {
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
