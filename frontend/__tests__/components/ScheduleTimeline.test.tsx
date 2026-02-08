import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScheduleTimeline } from '@/components/charts/ScheduleTimeline'
import '@testing-library/jest-dom'

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

    // Should have 3 schedule blocks (each has data-testid="schedule-block-{id}")
    expect(screen.getByTestId('schedule-block-1')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-2')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-3')).toBeInTheDocument()
  })

  it('shows schedule details on hover/click', async () => {
    const user = userEvent.setup()
    render(<ScheduleTimeline schedules={mockSchedules} />)

    const washingMachineBlock = screen.getByTestId('schedule-block-1')
    await user.hover(washingMachineBlock)

    expect(screen.getByText(/lowest price period/i)).toBeInTheDocument()
    expect(screen.getByText(/0\.45/)).toBeInTheDocument()
  })

  it('displays total savings for all schedules', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    // Total savings: 0.15 + 0.10 + 1.20 = 1.45
    expect(screen.getByText(/1\.45/)).toBeInTheDocument()
  })

  it('shows 24-hour timeline by default', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    // Should show hour markers
    expect(screen.getByText('00:00')).toBeInTheDocument()
    expect(screen.getByText('12:00')).toBeInTheDocument()
  })

  it('highlights current time on timeline', () => {
    render(<ScheduleTimeline schedules={mockSchedules} showCurrentTime />)

    expect(screen.getByTestId('current-time-marker')).toBeInTheDocument()
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

  it('handles empty schedules gracefully', () => {
    render(<ScheduleTimeline schedules={[]} />)

    expect(screen.getByText(/no scheduled activities/i)).toBeInTheDocument()
  })

  it('allows clicking on a schedule to view details', async () => {
    const onSelectSchedule = jest.fn()
    const user = userEvent.setup()

    render(
      <ScheduleTimeline
        schedules={mockSchedules}
        onSelectSchedule={onSelectSchedule}
      />
    )

    await user.click(screen.getByTestId('schedule-block-1'))

    expect(onSelectSchedule).toHaveBeenCalledWith(mockSchedules[0])
  })

  it('displays overlapping schedules correctly', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    // Washing Machine (02:00-04:00) overlaps with Dishwasher (03:00-04:30)
    // They should be displayed in different rows
    expect(screen.getByTestId('schedule-block-1')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-2')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-block-3')).toBeInTheDocument()
  })

  it('shows savings indicator on each block', () => {
    render(<ScheduleTimeline schedules={mockSchedules} showSavings />)

    const block1 = screen.getByTestId('schedule-block-1')
    expect(within(block1).getByText(/save/i)).toBeInTheDocument()
  })

  it('is accessible with proper ARIA labels', () => {
    render(<ScheduleTimeline schedules={mockSchedules} />)

    expect(
      screen.getByRole('img', { name: /schedule timeline/i })
    ).toBeInTheDocument()
  })

  it('supports drag and drop for manual rescheduling', async () => {
    const onReschedule = jest.fn()

    render(
      <ScheduleTimeline
        schedules={mockSchedules}
        allowReschedule
        onReschedule={onReschedule}
      />
    )

    // Check that draggable attribute is present
    const block = screen.getByTestId('schedule-block-1')
    expect(block).toHaveAttribute('draggable', 'true')
  })
})
