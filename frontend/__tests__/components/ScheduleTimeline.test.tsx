import React from 'react'
import { render, screen, within, fireEvent } from '@testing-library/react'
import { ScheduleTimeline } from '@/components/charts/ScheduleTimeline'
import '@testing-library/jest-dom'

// Mock date-fns functions that depend on wall-clock time so tests are deterministic.
// parseISO is left as a real pass-through; only the clock-dependent helpers are stubbed.
jest.mock('date-fns', () => {
  const actual = jest.requireActual<typeof import('date-fns')>('date-fns')
  return {
    ...actual,
    // Freeze "now" at 2026-02-06T10:00:00Z so showCurrentTime tests are stable
    startOfDay: jest.fn(() => new Date('2026-02-06T00:00:00Z')),
  }
})

jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (amount: number) => `$${amount.toFixed(2)}`,
}))

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

const mockSchedules = [
  {
    applianceId: '1',
    applianceName: 'Washing Machine',
    scheduledStart: '2026-02-06T02:00:00Z',
    scheduledEnd: '2026-02-06T04:00:00Z',
    estimatedCost: 0.45,
    savings: 0.15,
    reason: 'Lowest price period',
  },
  {
    applianceId: '2',
    applianceName: 'Dishwasher',
    scheduledStart: '2026-02-06T03:00:00Z',
    scheduledEnd: '2026-02-06T04:30:00Z',
    estimatedCost: 0.30,
    savings: 0.10,
    reason: 'Off-peak pricing',
  },
  {
    applianceId: '3',
    applianceName: 'EV Charger',
    scheduledStart: '2026-02-06T01:00:00Z',
    scheduledEnd: '2026-02-06T06:00:00Z',
    estimatedCost: 2.50,
    savings: 1.20,
    reason: 'Night rate',
  },
]

describe('ScheduleTimeline', () => {
  it('renders timeline with all scheduled appliances', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(screen.getByText('Washing Machine')).toBeInTheDocument()
    expect(screen.getByText('Dishwasher')).toBeInTheDocument()
    expect(screen.getByText('EV Charger')).toBeInTheDocument()
  })

  it('displays time blocks for each schedule', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(screen.getByTestId('schedule-block-1')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-2')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-3')).toBeInTheDocument()
  })

  it('shows schedule details on hover', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    const washingMachineBlock = screen.getByTestId('schedule-block-1')
    fireEvent.mouseEnter(washingMachineBlock)

    expect(screen.getByText(/lowest price period/i)).toBeInTheDocument()
    expect(screen.getByText(/0\.45/)).toBeInTheDocument()
  })

  it('hides schedule tooltip when mouse leaves the block', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    const block = screen.getByTestId('schedule-block-1')
    fireEvent.mouseEnter(block)

    expect(screen.getByText(/lowest price period/i)).toBeInTheDocument()

    fireEvent.mouseLeave(block)

    expect(screen.queryByText(/lowest price period/i)).not.toBeInTheDocument()
  })

  it('shows tooltip with cost and savings on hover', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    fireEvent.mouseEnter(screen.getByTestId('schedule-block-1'))

    expect(screen.getByText(/\$0\.45/)).toBeInTheDocument()
    expect(screen.getByText(/\$0\.15/)).toBeInTheDocument()
  })

  it('displays total savings for all schedules', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    // Total savings: 0.15 + 0.10 + 1.20 = 1.45
    expect(screen.getByText(/1\.45/)).toBeInTheDocument()
  })

  it('shows the "Today\'s Schedule" heading', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(screen.getByText("Today's Schedule")).toBeInTheDocument()
  })

  it('shows 24-hour timeline by default with hour labels', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(screen.getByText('00:00')).toBeInTheDocument()
    expect(screen.getByText('12:00')).toBeInTheDocument()
  })

  it('renders hour labels at 0, 3, 6 ... 24 intervals', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    const hourLabels = ['00:00', '03:00', '06:00', '09:00', '12:00', '15:00', '18:00', '21:00', '24:00']
    for (const label of hourLabels) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('highlights current time on timeline when showCurrentTime is true', () => {
    render(<ScheduleTimeline schedules={mockSchedules} showCurrentTime />)

    expect(screen.getByTestId('current-time-marker')).toBeInTheDocument()
  })

  it('does not render current time marker when showCurrentTime is false', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(screen.queryByTestId('current-time-marker')).not.toBeInTheDocument()
  })

  it('shows price zones on the timeline', () => {
    const priceZones = [
      { start: '01:00', end: '06:00', type: 'cheap' as const },
      { start: '17:00', end: '21:00', type: 'expensive' as const },
    ]

    render(<ScheduleTimeline schedules={mockSchedules} priceZones={priceZones} />)

    expect(screen.getByTestId('price-zone-cheap')).toBeInTheDocument()
    expect(screen.getByTestId('price-zone-expensive')).toBeInTheDocument()
  })

  it('renders moderate price zone when provided', () => {
    const priceZones = [{ start: '09:00', end: '12:00', type: 'moderate' as const }]

    render(<ScheduleTimeline schedules={mockSchedules} priceZones={priceZones} />)

    expect(screen.getByTestId('price-zone-moderate')).toBeInTheDocument()
  })

  it('handles empty schedules gracefully', () => {
    render(<ScheduleTimeline schedules={[]} />)

    expect(screen.getByText(/no scheduled activities/i)).toBeInTheDocument()
  })

  it('shows accessible role on the empty state element', () => {
    render(<ScheduleTimeline schedules={[]} />)

    expect(
      screen.getByRole('img', { name: /schedule timeline - no scheduled activities/i })
    ).toBeInTheDocument()
  })

  it('allows clicking on a schedule to invoke onSelectSchedule', () => {
    const onSelectSchedule = jest.fn()

    render(
      <ScheduleTimeline
        schedules={mockSchedules}
        onSelectSchedule={onSelectSchedule}
      />
    )

    fireEvent.click(screen.getByTestId('schedule-block-1'))

    expect(onSelectSchedule).toHaveBeenCalledTimes(1)
    expect(onSelectSchedule).toHaveBeenCalledWith(mockSchedules[0])
  })

  it('does not throw when clicking a block without onSelectSchedule', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(() => fireEvent.click(screen.getByTestId('schedule-block-1'))).not.toThrow()
  })

  it('displays overlapping schedules in separate rows', () => {
    // Washing Machine (02:00-04:00) overlaps Dishwasher (03:00-04:30);
    // EV Charger (01:00-06:00) overlaps both. All three must still appear.
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(screen.getByTestId('schedule-block-1')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-2')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-3')).toBeInTheDocument()
  })

  it('shows savings indicator on each block when showSavings is true', () => {
    render(<ScheduleTimeline schedules={mockSchedules} showSavings />)

    const block1 = screen.getByTestId('schedule-block-1')
    expect(within(block1).getByText(/save/i)).toBeInTheDocument()
  })

  it('shows savings amount in block when showSavings is true', () => {
    render(<ScheduleTimeline schedules={mockSchedules} showSavings />)

    const block1 = screen.getByTestId('schedule-block-1')
    expect(within(block1).getByText(/\$0\.15/)).toBeInTheDocument()
  })

  it('does not show savings text inside blocks when showSavings is false', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    const block1 = screen.getByTestId('schedule-block-1')
    expect(within(block1).queryByText(/save/i)).not.toBeInTheDocument()
  })

  it('is accessible with proper ARIA labels', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(
      screen.getByRole('img', { name: /schedule timeline/i })
    ).toBeInTheDocument()
  })

  it('aria-label on the timeline includes the schedule count', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    const timeline = screen.getByRole('img', { name: /schedule timeline/i })
    expect(timeline.getAttribute('aria-label')).toContain('3')
  })

  it('supports drag and drop: sets draggable attribute when allowReschedule is true', () => {
    render(
      <ScheduleTimeline
        schedules={mockSchedules}
        allowReschedule
        onReschedule={jest.fn()}
      />
    )

    const block = screen.getByTestId('schedule-block-1')
    expect(block).toHaveAttribute('draggable', 'true')
  })

  it('schedule blocks are not draggable when allowReschedule is false', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    const block = screen.getByTestId('schedule-block-1')
    expect(block).toHaveAttribute('draggable', 'false')
  })

  it('renders a single schedule without error', () => {
    const singleSchedule = [mockSchedules[0]]

    render(<ScheduleTimeline schedules={singleSchedule} />)

    expect(screen.getByText('Washing Machine')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-1')).toBeInTheDocument()
  })
})
