"use client";

import { useState } from "react";
import { useHeatingOilPrices } from "@/lib/hooks/useHeatingOil";
import { OilPriceHistory } from "./OilPriceHistory";
import { DealerList } from "./DealerList";
import { US_STATES } from "@/lib/constants/regions";

export function HeatingOilDashboard() {
  const [selectedState, setSelectedState] = useState<string | undefined>();
  const { data, isLoading, error } = useHeatingOilPrices();

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse rounded-lg bg-gray-100 h-16" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-danger-200 bg-danger-50 p-4 text-sm text-danger-700">
        Unable to load heating oil prices. Please try again later.
      </div>
    );
  }

  const prices = data?.prices || [];
  const trackedStates = data?.tracked_states || [];
  const nationalPrice = prices.find((p) => p.state === "US");
  const statePrices = prices.filter((p) => p.state !== "US");

  return (
    <div className="space-y-6">
      {/* National average */}
      {nationalPrice && (
        <div className="rounded-lg border bg-warning-50 p-4">
          <p className="text-sm font-medium text-warning-900">
            National Average
          </p>
          <p className="text-2xl font-bold text-warning-900">
            ${nationalPrice.price_per_gallon.toFixed(2)}/gallon
          </p>
          {nationalPrice.period_date && (
            <p className="text-xs text-warning-600">
              Week of {nationalPrice.period_date}
            </p>
          )}
        </div>
      )}

      {/* State selector */}
      <div>
        <label
          htmlFor="state-select"
          className="block text-sm font-medium text-gray-700"
        >
          Select State
        </label>
        <select
          id="state-select"
          value={selectedState || ""}
          onChange={(e) => setSelectedState(e.target.value || undefined)}
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        >
          <option value="">All States</option>
          {trackedStates.map((st) => (
            <option key={st} value={st}>
              {US_STATES[st] || st}
            </option>
          ))}
        </select>
      </div>

      {/* State price cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {statePrices
          .filter((p) => !selectedState || p.state === selectedState)
          .map((p) => {
            const diff = nationalPrice
              ? ((p.price_per_gallon - nationalPrice.price_per_gallon) /
                  nationalPrice.price_per_gallon) *
                100
              : null;

            return (
              <button
                type="button"
                key={p.state}
                className="rounded-lg border p-4 text-left cursor-pointer hover:border-primary-300 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                onClick={() => setSelectedState(p.state)}
              >
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-gray-900">
                    {US_STATES[p.state] || p.state}
                  </p>
                  {diff !== null && (
                    <span
                      className={`text-xs font-medium ${
                        diff < 0
                          ? "text-success-600"
                          : diff > 0
                            ? "text-danger-600"
                            : "text-gray-500"
                      }`}
                    >
                      {diff > 0 ? "+" : ""}
                      {diff.toFixed(1)}%
                    </span>
                  )}
                </div>
                <p className="text-lg font-bold text-gray-900">
                  ${p.price_per_gallon.toFixed(2)}/gal
                </p>
              </button>
            );
          })}
      </div>

      {/* Detail sections when a state is selected */}
      {selectedState && (
        <>
          <OilPriceHistory state={selectedState} />
          <DealerList state={selectedState} />
        </>
      )}
    </div>
  );
}
