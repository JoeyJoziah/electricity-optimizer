'use client'

import React, { useState } from 'react'
import { Header } from '@/components/layout/Header'
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input, Checkbox } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ScheduleTimeline } from '@/components/charts/ScheduleTimeline'
import { useOptimalSchedule, useAppliances, useSaveAppliances, usePotentialSavings } from '@/lib/hooks/useOptimization'
import { useSettingsStore } from '@/lib/store/settings'
import { formatCurrency, formatDuration } from '@/lib/utils/format'
import { cn } from '@/lib/utils/cn'
import {
  Plus,
  Trash2,
  Zap,
  Clock,
  DollarSign,
  Leaf,
  Settings,
  Play,
  Calendar,
  AlertCircle,
  Pencil,
  Check,
  X,
} from 'lucide-react'
import type { Appliance } from '@/types'

const DEFAULT_APPLIANCES: Partial<Appliance>[] = [
  { name: 'Washing Machine', powerKw: 2.0, typicalDurationHours: 2, priority: 'medium' },
  { name: 'Dishwasher', powerKw: 1.5, typicalDurationHours: 1.5, priority: 'low' },
  { name: 'Tumble Dryer', powerKw: 2.5, typicalDurationHours: 1, priority: 'low' },
  { name: 'EV Charger', powerKw: 7.0, typicalDurationHours: 4, priority: 'high' },
  { name: 'Heat Pump', powerKw: 3.0, typicalDurationHours: 8, priority: 'medium' },
]

export default function OptimizePage() {
  const [isEditing, setIsEditing] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<{ name: string; powerKw: number; typicalDurationHours: number }>({
    name: '', powerKw: 1, typicalDurationHours: 1,
  })
  const [newAppliance, setNewAppliance] = useState<Partial<Appliance>>({
    name: '',
    powerKw: 1.0,
    typicalDurationHours: 1,
    isFlexible: true,
    priority: 'medium',
  })

  const region = useSettingsStore((s) => s.region)
  const appliances = useSettingsStore((s) => s.appliances)
  const addAppliance = useSettingsStore((s) => s.addAppliance)
  const removeAppliance = useSettingsStore((s) => s.removeAppliance)
  const updateAppliance = useSettingsStore((s) => s.updateAppliance)

  // Fetch optimization data
  const { data: scheduleData, isLoading: scheduleLoading, refetch: refetchSchedule } =
    useOptimalSchedule({
      appliances,
      region,
      date: new Date().toISOString().split('T')[0],
    })

  const { data: savingsData } = usePotentialSavings(appliances, region)

  const startEdit = (appliance: Appliance) => {
    setEditingId(appliance.id)
    setEditForm({
      name: appliance.name,
      powerKw: appliance.powerKw,
      typicalDurationHours: appliance.typicalDurationHours,
    })
  }

  const saveEdit = () => {
    if (editingId && editForm.name) {
      updateAppliance(editingId, editForm)
      setEditingId(null)
    }
  }

  const cancelEdit = () => {
    setEditingId(null)
  }

  // Handle adding new appliance
  const handleAddAppliance = () => {
    if (!newAppliance.name) return

    addAppliance({
      id: Date.now().toString(),
      name: newAppliance.name,
      powerKw: newAppliance.powerKw || 1,
      typicalDurationHours: newAppliance.typicalDurationHours || 1,
      isFlexible: newAppliance.isFlexible ?? true,
      priority: newAppliance.priority || 'medium',
    })

    setNewAppliance({
      name: '',
      powerKw: 1.0,
      typicalDurationHours: 1,
      isFlexible: true,
      priority: 'medium',
    })
  }

  // Handle quick add from defaults
  const handleQuickAdd = (preset: Partial<Appliance>) => {
    addAppliance({
      id: Date.now().toString(),
      name: preset.name!,
      powerKw: preset.powerKw || 1,
      typicalDurationHours: preset.typicalDurationHours || 1,
      isFlexible: true,
      priority: preset.priority || 'medium',
    })
  }

  // Run optimization
  const handleOptimize = () => {
    refetchSchedule()
  }

  const schedules = scheduleData?.schedules || []
  const totalSavings = scheduleData?.totalSavings || 0

  return (
    <div className="flex flex-col">
      <Header title="Load Optimization" />

      <div className="p-6">
        {/* Stats row */}
        <div className="mb-6 grid gap-4 md:grid-cols-4">
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-primary-100 p-3">
                <Zap className="h-6 w-6 text-primary-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Appliances</p>
                <p className="text-2xl font-bold text-gray-900">
                  {appliances.length}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-success-100 p-3">
                <DollarSign className="h-6 w-6 text-success-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Daily Savings</p>
                <p className="text-2xl font-bold text-success-600">
                  {savingsData?.dailySavings
                    ? formatCurrency(savingsData.dailySavings)
                    : '--'}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-warning-100 p-3">
                <Calendar className="h-6 w-6 text-warning-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Monthly Savings</p>
                <p className="text-2xl font-bold text-warning-600">
                  {savingsData?.monthlySavings
                    ? formatCurrency(savingsData.monthlySavings)
                    : '--'}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-primary-100 p-3">
                <Leaf className="h-6 w-6 text-primary-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Annual Savings</p>
                <p className="text-2xl font-bold text-primary-600">
                  {savingsData?.annualSavings
                    ? formatCurrency(savingsData.annualSavings)
                    : '--'}
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Appliances configuration */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Your Appliances</CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsEditing(!isEditing)}
                  >
                    <Settings className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {appliances.length === 0 ? (
                  <div className="py-8 text-center">
                    <Zap className="mx-auto h-12 w-12 text-gray-300" />
                    <p className="mt-2 text-gray-500">No appliances added yet</p>
                    <p className="text-sm text-gray-400">
                      Add your appliances to start optimizing
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {appliances.map((appliance) => (
                      <div
                        key={appliance.id}
                        className="rounded-lg border border-gray-200 p-3"
                      >
                        {editingId === appliance.id ? (
                          <div className="space-y-2">
                            <Input
                              value={editForm.name}
                              onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                              placeholder="Name"
                            />
                            <div className="grid grid-cols-2 gap-2">
                              <Input
                                type="number"
                                step="0.1"
                                value={editForm.powerKw}
                                onChange={(e) => setEditForm((f) => ({ ...f, powerKw: parseFloat(e.target.value) || 0 }))}
                                placeholder="kW"
                              />
                              <Input
                                type="number"
                                step="0.5"
                                value={editForm.typicalDurationHours}
                                onChange={(e) => setEditForm((f) => ({ ...f, typicalDurationHours: parseFloat(e.target.value) || 0 }))}
                                placeholder="Hours"
                              />
                            </div>
                            <div className="flex justify-end gap-2">
                              <Button variant="ghost" size="sm" onClick={cancelEdit}>
                                <X className="h-4 w-4" />
                              </Button>
                              <Button variant="primary" size="sm" onClick={saveEdit}>
                                <Check className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <Checkbox
                                label=""
                                checked={appliance.isFlexible}
                                onChange={(e) =>
                                  updateAppliance(appliance.id, {
                                    isFlexible: e.target.checked,
                                  })
                                }
                              />
                              <div>
                                <p className="font-medium text-gray-900">
                                  {appliance.name}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {appliance.powerKw}kW -{' '}
                                  {formatDuration(appliance.typicalDurationHours)}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge
                                variant={
                                  appliance.priority === 'high'
                                    ? 'danger'
                                    : appliance.priority === 'medium'
                                      ? 'warning'
                                      : 'default'
                                }
                                size="sm"
                              >
                                {appliance.priority}
                              </Badge>
                              {isEditing && (
                                <>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => startEdit(appliance)}
                                  >
                                    <Pencil className="h-4 w-4 text-gray-500" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => removeAppliance(appliance.id)}
                                  >
                                    <Trash2 className="h-4 w-4 text-danger-500" />
                                  </Button>
                                </>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Quick add section */}
                <div className="mt-4 border-t border-gray-200 pt-4">
                  <p className="mb-2 text-sm font-medium text-gray-700">
                    Quick Add
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {DEFAULT_APPLIANCES.filter(
                      (d) => !appliances.some((a) => a.name === d.name)
                    ).map((preset) => (
                      <Button
                        key={preset.name}
                        variant="outline"
                        size="sm"
                        onClick={() => handleQuickAdd(preset)}
                      >
                        <Plus className="mr-1 h-3 w-3" />
                        {preset.name}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* Custom add */}
                <div className="mt-4 space-y-3 border-t border-gray-200 pt-4">
                  <p className="text-sm font-medium text-gray-700">
                    Add Custom
                  </p>
                  <Input
                    placeholder="Appliance name"
                    value={newAppliance.name}
                    onChange={(e) =>
                      setNewAppliance((a) => ({ ...a, name: e.target.value }))
                    }
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      type="number"
                      placeholder="Power (kW)"
                      value={newAppliance.powerKw}
                      onChange={(e) =>
                        setNewAppliance((a) => ({
                          ...a,
                          powerKw: parseFloat(e.target.value),
                        }))
                      }
                    />
                    <Input
                      type="number"
                      placeholder="Duration (hrs)"
                      value={newAppliance.typicalDurationHours}
                      onChange={(e) =>
                        setNewAppliance((a) => ({
                          ...a,
                          typicalDurationHours: parseFloat(e.target.value),
                        }))
                      }
                    />
                  </div>
                  <Button
                    variant="primary"
                    className="w-full"
                    onClick={handleAddAppliance}
                    disabled={!newAppliance.name}
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    Add Appliance
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Schedule and results */}
          <div className="lg:col-span-2 space-y-6">
            {/* Run optimization */}
            <Card>
              <CardContent className="p-4">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div className="flex items-center gap-3">
                    <Clock className="h-8 w-8 text-primary-600" />
                    <div>
                      <p className="font-semibold text-gray-900">
                        Optimize Your Schedule
                      </p>
                      <p className="text-sm text-gray-500">
                        Find the best times to run your appliances
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    onClick={handleOptimize}
                    disabled={appliances.length === 0 || scheduleLoading}
                    loading={scheduleLoading}
                  >
                    <Play className="mr-2 h-4 w-4" />
                    Optimize Now
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Results */}
            {scheduleLoading ? (
              <Card>
                <CardContent className="p-4">
                  <Skeleton variant="rectangular" height={200} />
                </CardContent>
              </Card>
            ) : schedules.length > 0 ? (
              <>
                {/* Savings summary */}
                <Card className="border-success-200 bg-success-50">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-success-700">
                          Total savings today
                        </p>
                        <p className="text-3xl font-bold text-success-800">
                          {formatCurrency(totalSavings)}
                        </p>
                      </div>
                      <Leaf className="h-12 w-12 text-success-600" />
                    </div>
                  </CardContent>
                </Card>

                {/* Timeline */}
                <Card>
                  <CardHeader>
                    <CardTitle>Optimized Schedule</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ScheduleTimeline
                      schedules={schedules}
                      showCurrentTime
                      showSavings
                      priceZones={[
                        { start: '01:00', end: '06:00', type: 'cheap' },
                        { start: '17:00', end: '21:00', type: 'expensive' },
                      ]}
                    />
                  </CardContent>
                </Card>

                {/* Schedule details */}
                <Card>
                  <CardHeader>
                    <CardTitle>Schedule Details</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {schedules.map((schedule) => (
                        <div
                          key={schedule.applianceId}
                          className="flex items-center justify-between rounded-lg border border-gray-200 p-4"
                        >
                          <div>
                            <p className="font-medium text-gray-900">
                              {schedule.applianceName}
                            </p>
                            <p className="text-sm text-gray-500">
                              {schedule.reason}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="font-medium text-gray-900">
                              {new Date(schedule.scheduledStart).toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                              {' - '}
                              {new Date(schedule.scheduledEnd).toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                            <p className="text-sm text-success-600">
                              Save {formatCurrency(schedule.savings)}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </>
            ) : appliances.length > 0 ? (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <AlertCircle className="h-12 w-12 text-gray-300" />
                  <p className="mt-4 text-gray-500">
                    Click "Optimize Now" to generate your schedule
                  </p>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <Zap className="h-12 w-12 text-gray-300" />
                  <p className="mt-4 text-gray-500">
                    Add appliances to start optimizing
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
