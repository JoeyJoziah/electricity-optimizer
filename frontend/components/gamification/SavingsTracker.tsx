'use client'

import React from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils/format'
import { cn } from '@/lib/utils/cn'
import { TrendingUp, Flame, Target, Award } from 'lucide-react'

interface SavingsTrackerProps {
  dailySavings: number
  weeklySavings: number
  monthlySavings: number
  streakDays: number
  bestStreak: number
  optimizationScore: number // 0-100
}

export function SavingsTracker({
  dailySavings,
  weeklySavings,
  monthlySavings,
  streakDays,
  bestStreak,
  optimizationScore,
}: SavingsTrackerProps) {
  const streakLevel =
    streakDays >= 30
      ? 'legendary'
      : streakDays >= 14
        ? 'gold'
        : streakDays >= 7
          ? 'silver'
          : 'bronze'

  const streakColors = {
    bronze: 'text-amber-600 bg-amber-50 border-amber-200',
    silver: 'text-gray-500 bg-gray-50 border-gray-200',
    gold: 'text-yellow-600 bg-yellow-50 border-yellow-200',
    legendary: 'text-purple-600 bg-purple-50 border-purple-200',
  }

  return (
    <div className="space-y-4" data-testid="savings-tracker">
      {/* Savings summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg bg-success-50 p-3 text-center">
          <p className="text-xs font-medium text-success-600">Today</p>
          <p className="mt-1 text-lg font-bold text-success-700">
            {formatCurrency(dailySavings)}
          </p>
        </div>
        <div className="rounded-lg bg-success-50 p-3 text-center">
          <p className="text-xs font-medium text-success-600">This Week</p>
          <p className="mt-1 text-lg font-bold text-success-700">
            {formatCurrency(weeklySavings)}
          </p>
        </div>
        <div className="rounded-lg bg-success-50 p-3 text-center">
          <p className="text-xs font-medium text-success-600">This Month</p>
          <p className="mt-1 text-lg font-bold text-success-700">
            {formatCurrency(monthlySavings)}
          </p>
        </div>
      </div>

      {/* Streak and Score row */}
      <div className="flex items-center gap-3">
        {/* Streak */}
        <div
          className={cn(
            'flex flex-1 items-center gap-2 rounded-lg border p-3',
            streakColors[streakLevel]
          )}
        >
          <Flame className="h-5 w-5" />
          <div>
            <p className="text-sm font-bold">{streakDays}-day streak</p>
            <p className="text-xs opacity-75">Best: {bestStreak} days</p>
          </div>
        </div>

        {/* Optimization Score */}
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-primary-200 bg-primary-50 p-3">
          <Target className="h-5 w-5 text-primary-600" />
          <div>
            <p className="text-sm font-bold text-primary-700">
              {optimizationScore}/100
            </p>
            <p className="text-xs text-primary-500">Optimization Score</p>
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div>
        <div className="mb-1 flex items-center justify-between text-xs text-gray-500">
          <span>Monthly Goal: {formatCurrency(50)}</span>
          <span>{Math.min(Math.round((monthlySavings / 50) * 100), 100)}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
          <div
            className="h-full rounded-full bg-success-500 transition-all duration-500"
            style={{
              width: `${Math.min((monthlySavings / 50) * 100, 100)}%`,
            }}
          />
        </div>
      </div>
    </div>
  )
}
