"use client";

import React from "react";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SwitchDecision } from "@/lib/api/agent-switcher";
import {
  decisionBadge,
  formatCurrency,
  formatRate,
} from "./decisionPresentation";

interface CheckNowResultProps {
  result: SwitchDecision;
  onDismiss: () => void;
}

/**
 * Renders the result of an on-demand /check-now evaluation.
 * Pure presentational — the decision lives in the parent's local state
 * (it is the mutation's resolved value, not a server cache entry).
 */
export default function CheckNowResult({
  result,
  onDismiss,
}: CheckNowResultProps) {
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
