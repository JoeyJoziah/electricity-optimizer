'use client'

import React, { useMemo, useState } from 'react'
import { format, parseISO, differenceInMinutes, startOfDay, addHours } from 'date-fns'
import { cn } from '@/lib/utils/cn'
import { formatCurrency } from '@/lib/utils/format'
import type { OptimizationSchedule } from '@/types'

export interface PriceZone {
  start: string
  end: string
  type: 'cheap' | 'moderate' | 'expensive'
}

export interface ScheduleTimelineProps {
  schedules: OptimizationSchedule[]
  priceZones?: PriceZone[]
  showCurrentTime?: boolean
  showSavings?: boolean
  allowReschedule?: boolean
  onSelectSchedule?: (schedule: OptimizationSchedule) => void
  onReschedule?: (
    schedule: OptimizationSchedule,
    newStart: Date,
    newEnd: Date
  ) => void
  className?: string
}

const HOURS = Array.from({ length: 25 }, (_, i) => i)
const TIMELINE_HEIGHT = 60

const priceZoneColors = {
  cheap: 'bg-success-100',
  moderate: 'bg-warning-100',
  expensive: 'bg-danger-100',
}

export const ScheduleTimeline: React.FC<ScheduleTimelineProps> = ({
  schedules,
  priceZones = [],
  showCurrentTime = false,
  showSavings = false,
  allowReschedule = false,
  onSelectSchedule,
  onReschedule,
  className,
}) => {
  const [hoveredSchedule, setHoveredSchedule] = useState<string | null>(null)
  const [draggedSchedule, setDraggedSchedule] = useState<string | null>(null)

  // Calculate total savings
  const totalSavings = useMemo(() => {
    return schedules.reduce((sum, s) => sum + s.savings, 0)
  }, [schedules])

  // Get current time position
  const currentTimePosition = useMemo(() => {
    if (!showCurrentTime) return null
    const now = new Date()
    const minutesSinceMidnight = now.getHours() * 60 + now.getMinutes()
    return (minutesSinceMidnight / (24 * 60)) * 100
  }, [showCurrentTime])

  // Group schedules into rows to avoid overlap
  const scheduleRows = useMemo(() => {
    const rows: OptimizationSchedule[][] = []

    schedules.forEach((schedule) => {
      const start = parseISO(schedule.scheduledStart)
      const end = parseISO(schedule.scheduledEnd)

      // Find a row where this schedule doesn't overlap
      let placed = false
      for (const row of rows) {
        const hasOverlap = row.some((s) => {
          const sStart = parseISO(s.scheduledStart)
          const sEnd = parseISO(s.scheduledEnd)
          return !(end <= sStart || start >= sEnd)
        })

        if (!hasOverlap) {
          row.push(schedule)
          placed = true
          break
        }
      }

      if (!placed) {
        rows.push([schedule])
      }
    })

    return rows
  }, [schedules])

  // Calculate schedule block position
  const getSchedulePosition = (schedule: OptimizationSchedule) => {
    const start = parseISO(schedule.scheduledStart)
    const end = parseISO(schedule.scheduledEnd)
    const today = startOfDay(new Date())

    const startMinutes = differenceInMinutes(start, today)
    const endMinutes = differenceInMinutes(end, today)

    const left = (startMinutes / (24 * 60)) * 100
    const width = ((endMinutes - startMinutes) / (24 * 60)) * 100

    return { left: `${left}%`, width: `${width}%` }
  }

  // Handle drag start
  const handleDragStart = (e: React.DragEvent, scheduleId: string) => {
    if (!allowReschedule) return
    setDraggedSchedule(scheduleId)
    e.dataTransfer.setData('text/plain', scheduleId)
  }

  // Empty state
  if (schedules.length === 0) {
    return (
      <div
        className={cn(
          'flex h-48 items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50',
          className
        )}
        role="img"
        aria-label="Schedule timeline - no scheduled activities"
      >
        <p className="text-gray-500">No scheduled activities</p>
      </div>
    )
  }

  return (
    <div
      className={cn('', className)}
      role="img"
      aria-label={`Schedule timeline showing ${schedules.length} scheduled activities with total savings of ${formatCurrency(totalSavings)}`}
    >
      {/* Header with total savings */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">Today's Schedule</h3>
        <div className="text-sm">
          Total savings:{' '}
          <span className="font-semibold text-success-600">
            {formatCurrency(totalSavings)}
          </span>
        </div>
      </div>

      {/* Timeline container */}
      <div className="relative overflow-hidden rounded-lg border border-gray-200 bg-white">
        {/* Hour labels */}
        <div className="relative h-6 border-b border-gray-200 bg-gray-50">
          {HOURS.filter((h) => h % 3 === 0).map((hour) => (
            <span
              key={hour}
              className="absolute -translate-x-1/2 text-xs text-gray-500"
              style={{ left: `${(hour / 24) * 100}%` }}
            >
              {String(hour).padStart(2, '0')}:00
            </span>
          ))}
        </div>

        {/* Price zones */}
        <div className="relative h-4">
          {priceZones.map((zone, i) => {
            const [startHour, startMin] = zone.start.split(':').map(Number)
            const [endHour, endMin] = zone.end.split(':').map(Number)
            const startPercent =
              ((startHour * 60 + startMin) / (24 * 60)) * 100
            const endPercent = ((endHour * 60 + endMin) / (24 * 60)) * 100
            const width = endPercent - startPercent

            return (
              <div
                key={i}
                data-testid={`price-zone-${zone.type}`}
                className={cn('absolute h-full', priceZoneColors[zone.type])}
                style={{ left: `${startPercent}%`, width: `${width}%` }}
              />
            )
          })}
        </div>

        {/* Schedule rows */}
        <div className="relative min-h-[80px]">
          {scheduleRows.map((row, rowIndex) => (
            <div
              key={rowIndex}
              className="relative"
              style={{ height: `${TIMELINE_HEIGHT}px` }}
            >
              {row.map((schedule) => {
                const position = getSchedulePosition(schedule)
                const isHovered = hoveredSchedule === schedule.applianceId

                return (
                  <div
                    key={schedule.applianceId}
                    data-testid={`schedule-block-${schedule.applianceId}`}
                    className={cn(
                      'absolute top-2 flex cursor-pointer flex-col justify-center rounded-md px-2 py-1 text-xs transition-all',
                      'border border-primary-300 bg-primary-100 text-primary-900',
                      isHovered && 'ring-2 ring-primary-500 z-10'
                    )}
                    style={{
                      left: position.left,
                      width: position.width,
                      minWidth: '60px',
                      height: `${TIMELINE_HEIGHT - 16}px`,
                    }}
                    onClick={() => onSelectSchedule?.(schedule)}
                    onMouseEnter={() => setHoveredSchedule(schedule.applianceId)}
                    onMouseLeave={() => setHoveredSchedule(null)}
                    draggable={allowReschedule}
                    onDragStart={(e) =>
                      handleDragStart(e, schedule.applianceId)
                    }
                  >
                    <span className="truncate font-medium">
                      {schedule.applianceName}
                    </span>
                    {showSavings && (
                      <span className="text-success-700">
                        Save {formatCurrency(schedule.savings)}
                      </span>
                    )}

                    {/* Tooltip on hover */}
                    {isHovered && (
                      <div className="absolute left-0 top-full z-20 mt-1 w-48 rounded-lg border border-gray-200 bg-white p-2 shadow-lg">
                        <p className="font-medium">{schedule.applianceName}</p>
                        <p className="text-gray-600">{schedule.reason}</p>
                        <p className="mt-1">
                          Cost: {formatCurrency(schedule.estimatedCost)}
                        </p>
                        <p className="text-success-600">
                          Savings: {formatCurrency(schedule.savings)}
                        </p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ))}

          {/* Current time marker */}
          {showCurrentTime && currentTimePosition !== null && (
            <div
              data-testid="current-time-marker"
              className="absolute top-0 z-30 h-full w-0.5 bg-danger-500"
              style={{ left: `${currentTimePosition}%` }}
            >
              <div className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-danger-500" />
            </div>
          )}
        </div>

        {/* Grid lines */}
        <div className="pointer-events-none absolute inset-0 top-6">
          {HOURS.filter((h) => h % 6 === 0).map((hour) => (
            <div
              key={hour}
              className="absolute h-full w-px bg-gray-200"
              style={{ left: `${(hour / 24) * 100}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
