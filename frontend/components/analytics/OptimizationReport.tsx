"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useOptimizationReport } from "@/lib/hooks/useReports";

const UTILITY_LABELS: Record<string, string> = {
  electricity: "Electricity",
  natural_gas: "Natural Gas",
  heating_oil: "Heating Oil",
  propane: "Propane",
  water: "Water",
};

interface OptimizationReportProps {
  state?: string;
}

export function OptimizationReport({ state }: OptimizationReportProps) {
  const { data: report, isLoading, error } = useOptimizationReport(state);

  if (!state) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Spend Optimization</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-500">
            Select a state to view your optimization report.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Spend Optimization Report</CardTitle>
        <p className="text-sm text-gray-500">
          Multi-utility spend analysis for {state}
        </p>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="py-8 text-center text-sm text-gray-500">
            Generating optimization report...
          </div>
        )}

        {error && (
          <div className="rounded-md bg-danger-50 p-3 text-sm text-danger-700">
            {error instanceof Error ? error.message : "Failed to load report"}
          </div>
        )}

        {report && (
          <div className="space-y-6">
            {/* Summary */}
            <div className="grid grid-cols-3 gap-4 rounded-lg bg-gray-50 p-4">
              <div>
                <p className="text-xs text-gray-500">Monthly Spend</p>
                <p className="text-2xl font-bold">
                  ${report.total_monthly_spend.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Annual Spend</p>
                <p className="text-2xl font-bold">
                  ${report.total_annual_spend.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Potential Savings</p>
                <p className="text-2xl font-bold text-success-600">
                  ${report.total_potential_monthly_savings.toFixed(2)}/mo
                </p>
              </div>
            </div>

            {/* Utility breakdown */}
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-3">
                Utility Breakdown ({report.utility_count} tracked)
              </h3>
              <div className="space-y-2">
                {report.utilities.map((u) => (
                  <div
                    key={u.utility_type}
                    className="flex items-center justify-between rounded-md border p-3"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        {UTILITY_LABELS[u.utility_type] || u.utility_type}
                      </p>
                      <p className="text-xs text-gray-500">
                        {u.current_rate.toFixed(4)} {u.unit} &middot;{" "}
                        {u.monthly_consumption} {u.consumption_unit}/mo
                      </p>
                    </div>
                    <p className="text-sm font-semibold">
                      ${u.monthly_cost.toFixed(2)}/mo
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* Savings opportunities */}
            {report.savings_opportunities.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">
                  Top Savings Opportunities
                </h3>
                <div className="space-y-2">
                  {report.savings_opportunities.map((opp) => (
                    <div
                      key={`${opp.utility_type}-${opp.action}-${opp.difficulty}`}
                      className="rounded-md border border-success-200 bg-success-50 p-3"
                    >
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-success-800">
                          {opp.action}
                        </p>
                        <p className="text-sm font-bold text-success-700">
                          Save ${opp.monthly_savings.toFixed(2)}/mo
                        </p>
                      </div>
                      <p className="text-xs text-success-600 mt-1">
                        {UTILITY_LABELS[opp.utility_type]} &middot; $
                        {opp.annual_savings.toFixed(2)}/yr &middot; Difficulty:{" "}
                        {opp.difficulty}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
