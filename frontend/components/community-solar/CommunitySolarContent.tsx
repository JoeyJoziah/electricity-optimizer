'use client'

import React, { useState } from 'react'
import { useSettingsStore } from '@/lib/store/settings'
import {
  useCommunitySolarPrograms,
  useCommunitySolarStates,
} from '@/lib/hooks/useCommunitySolar'
import { CommunitySolarService } from './SavingsCalculator'
import { Sun, ExternalLink, Users, MapPin } from 'lucide-react'
import { isSafeHref } from '@/lib/utils/url'

export default function CommunitySolarContent() {
  const region = useSettingsStore((s) => s.region)
  const stateCode = region?.startsWith('us_')
    ? region.slice(3).toUpperCase()
    : null

  const [filter, setFilter] = useState<'open' | 'waitlist' | undefined>(
    undefined
  )

  const { data: programsData, isLoading: programsLoading } =
    useCommunitySolarPrograms(stateCode, filter)
  const { data: statesData } = useCommunitySolarStates()

  if (!region) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <Sun className="h-12 w-12 text-gray-300 mb-4" />
        <h2 className="text-lg font-semibold text-gray-900">No region set</h2>
        <p className="text-sm text-gray-500 mt-1">
          Set your region in Settings to browse community solar programs.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Community Solar</h1>
        <p className="text-sm text-gray-500 mt-1">
          Subscribe to a local solar farm and save on your electricity bill — no
          rooftop panels needed.
        </p>
      </div>

      {/* Savings Calculator */}
      <CommunitySolarService />

      {/* State Coverage */}
      {statesData && statesData.total_states > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-3">
            <MapPin className="h-5 w-5 text-primary-600" />
            <h2 className="text-lg font-semibold text-gray-900">
              Available in {statesData.total_states} States
            </h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {statesData.states.map((s) => (
              <span
                key={s.state}
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  s.state === stateCode
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-600'
                }`}
              >
                {s.state} ({s.program_count})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700">Filter:</span>
        <button
          onClick={() => setFilter(undefined)}
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            !filter
              ? 'bg-primary-100 text-primary-700'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          All
        </button>
        <button
          onClick={() => setFilter('open')}
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            filter === 'open'
              ? 'bg-success-100 text-success-700'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Open
        </button>
        <button
          onClick={() => setFilter('waitlist')}
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            filter === 'waitlist'
              ? 'bg-warning-100 text-warning-700'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Waitlist
        </button>
      </div>

      {/* Programs List */}
      {programsLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="animate-pulse rounded-lg border border-gray-200 bg-white p-5"
            >
              <div className="h-5 bg-gray-200 rounded w-1/3 mb-3" />
              <div className="h-4 bg-gray-200 rounded w-2/3 mb-2" />
              <div className="h-4 bg-gray-200 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : programsData && programsData.count > 0 ? (
        <div className="space-y-4">
          {programsData.programs.map((program) => (
            <div
              key={program.id}
              className="rounded-lg border border-gray-200 bg-white p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-semibold text-gray-900">
                      {program.program_name}
                    </h3>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        program.enrollment_status === 'open'
                          ? 'bg-success-100 text-success-700'
                          : program.enrollment_status === 'waitlist'
                          ? 'bg-warning-100 text-warning-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {program.enrollment_status === 'open'
                        ? 'Open'
                        : program.enrollment_status === 'waitlist'
                        ? 'Waitlist'
                        : 'Closed'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-1">
                    by {program.provider}
                  </p>
                  {program.description && (
                    <p className="text-sm text-gray-700 mt-2">
                      {program.description}
                    </p>
                  )}
                </div>

                {program.savings_percent && (
                  <div className="text-right ml-4 flex-shrink-0">
                    <p className="text-2xl font-bold text-success-600">
                      {program.savings_percent}%
                    </p>
                    <p className="text-xs text-gray-500">savings</p>
                  </div>
                )}
              </div>

              {/* Details row */}
              <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
                {program.capacity_kw && (
                  <span>
                    Capacity: {Number(program.capacity_kw).toLocaleString()} kW
                  </span>
                )}
                {program.spots_available !== null && (
                  <span className="flex items-center gap-1">
                    <Users className="h-3 w-3" />
                    {program.spots_available} spots available
                  </span>
                )}
                {program.contract_months && (
                  <span>{program.contract_months} month contract</span>
                )}
                {program.min_bill_amount && (
                  <span>Min bill: ${program.min_bill_amount}</span>
                )}
              </div>

              {/* CTA */}
              {program.enrollment_url && isSafeHref(program.enrollment_url) && (
                <div className="mt-4">
                  <a
                    href={program.enrollment_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
                  >
                    {program.enrollment_status === 'open'
                      ? 'Enroll Now'
                      : 'Join Waitlist'}
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-gray-200 bg-white p-8 text-center">
          <Sun className="mx-auto h-10 w-10 text-gray-300 mb-3" />
          <p className="text-sm text-gray-500">
            No community solar programs found for your state
            {filter ? ` with status "${filter}"` : ''}.
          </p>
        </div>
      )}
    </div>
  )
}
