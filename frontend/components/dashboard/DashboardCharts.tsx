import React from 'react'
import Link from 'next/link'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ChartSkeleton } from '@/components/ui/skeleton'
import { SavingsTracker } from '@/components/gamification/SavingsTracker'
import { ArrowRight } from 'lucide-react'
import dynamic from 'next/dynamic'
import type { DashboardChartsProps } from './DashboardTypes'

const PriceLineChart = dynamic(
  () => import('@/components/charts/PriceLineChart').then((m) => m.PriceLineChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
)

/**
 * Renders the main charts row: Price History (2-column) and Savings Tracker (1-column).
 */
export function DashboardCharts({
  chartData,
  historyLoading,
  timeRange,
  onTimeRangeChange,
  savingsData,
}: DashboardChartsProps) {
  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-3">
      {/* Price chart - 2 columns */}
      <Card className="lg:col-span-2">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Price History</CardTitle>
            <Link href="/prices">
              <Button variant="ghost" size="sm">
                View all prices
                <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          <PriceLineChart
            data={chartData}
            loading={historyLoading}
            timeRange={timeRange}
            onTimeRangeChange={onTimeRangeChange}
            showCurrentPrice
            showTrend
            highlightOptimal
            height={300}
          />
        </CardContent>
      </Card>

      {/* Savings tracker with gamification */}
      <Card>
        <CardHeader>
          <CardTitle>Savings & Streaks</CardTitle>
        </CardHeader>
        <CardContent>
          <SavingsTracker
            dailySavings={savingsData ? savingsData.weekly / 7 : 0}
            weeklySavings={savingsData?.weekly ?? 0}
            monthlySavings={savingsData?.monthly ?? 0}
            streakDays={savingsData?.streak_days ?? 0}
            bestStreak={savingsData?.streak_days ?? 0}
            optimizationScore={0}
          />
        </CardContent>
      </Card>
    </div>
  )
}
