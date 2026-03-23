"use client";

import { useState } from "react";
import { WaterRateBenchmark } from "./WaterRateBenchmark";
import { WaterTierCalculator } from "./WaterTierCalculator";
import { ConservationTips } from "./ConservationTips";
import { US_STATES } from "@/lib/constants/regions";

export function WaterDashboard() {
  const [selectedState, setSelectedState] = useState<string>("");

  return (
    <div className="space-y-6">
      {/* Info banner */}
      <div className="rounded-lg border bg-cyan-50 p-4">
        <p className="text-sm font-medium text-cyan-900">
          Water Rate Benchmarking
        </p>
        <p className="text-sm text-cyan-700 mt-1">
          Compare municipal water rates in your area. Water utilities are
          geographic monopolies — this tool helps you understand your rates and
          find ways to conserve.
        </p>
      </div>

      {/* State selector */}
      <div>
        <label
          htmlFor="water-state-select"
          className="block text-sm font-medium text-gray-700"
        >
          Select State
        </label>
        <select
          id="water-state-select"
          value={selectedState}
          onChange={(e) => setSelectedState(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-cyan-500 focus:ring-cyan-500 sm:text-sm"
        >
          <option value="">Choose a state...</option>
          {Object.entries(US_STATES).map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
      </div>

      {/* State-specific sections */}
      {selectedState && (
        <>
          <WaterRateBenchmark state={selectedState} />
          <WaterTierCalculator state={selectedState} />
        </>
      )}

      {/* Conservation tips (always visible) */}
      <ConservationTips />
    </div>
  );
}
