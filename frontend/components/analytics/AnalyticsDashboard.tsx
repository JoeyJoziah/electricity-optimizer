"use client";

import { useState } from "react";
import { ForecastWidget } from "./ForecastWidget";
import { OptimizationReport } from "./OptimizationReport";
import { DataExport } from "./DataExport";
import { US_STATES_ABBR } from "@/lib/constants/regions";

export function AnalyticsDashboard() {
  const [state, setState] = useState("CT");

  return (
    <div className="space-y-6">
      {/* State selector */}
      <div className="flex items-center gap-3">
        <label
          htmlFor="state-select"
          className="text-sm font-medium text-gray-700"
        >
          State
        </label>
        <select
          id="state-select"
          value={state}
          onChange={(e) => setState(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        >
          {US_STATES_ABBR.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Forecast (Pro tier) */}
      <ForecastWidget state={state} />

      {/* Optimization Report (Business tier) */}
      <OptimizationReport state={state} />

      {/* Data Export (Business tier) */}
      <DataExport state={state} />
    </div>
  );
}
