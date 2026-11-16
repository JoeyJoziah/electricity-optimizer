import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { ScheduleTimeline } from "@/components/charts/ScheduleTimeline";
import type { OptimizationSchedule } from "@/types";
import { within } from "@testing-library/react";

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));
jest.mock("@/lib/utils/format", () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
}));
jest.mock("date-fns", () => ({
  parseISO: (s: string) => new Date(s),
  differenceInMinutes: (a: Date, b: Date) =>
    Math.floor((a.getTime() - b.getTime()) / 60000),
  startOfDay: (d: Date) => new Date(d.toDateString()),
}));

const makeSchedule = (
  id: string,
  start: string,
  end: string,
  savings = 10,
): OptimizationSchedule =>
  ({
    id,
    applianceId: id,
    applianceName: `Appliance ${id}`,
    startTime: start,
    endTime: end,
    savings,
    reason: "cheap time",
  }) as unknown as OptimizationSchedule;

const today = new Date().toISOString().split("T")[0];

describe("ScheduleTimeline", () => {
  it("shows empty state when no schedules", () => {
    render(<ScheduleTimeline schedules={[]} />);
    expect(
      screen.getByRole("img", {
        name: /no scheduled activities/i,
      }),
    ).toBeInTheDocument();
  });

  it("renders schedule blocks for each schedule", () => {
    const schedules = [
      makeSchedule("washer", `${today}T08:00:00`, `${today}T09:00:00`),
      makeSchedule("dryer", `${today}T10:00:00`, `${today}T11:00:00`),
    ];
    render(<ScheduleTimeline schedules={schedules} />);
    expect(screen.getByTestId("schedule-block-washer")).toBeInTheDocument();
    expect(screen.getByTestId("schedule-block-dryer")).toBeInTheDocument();
  });

  it("calls onSelectSchedule when a schedule block is clicked", () => {
    const onSelect = jest.fn();
    const schedules = [
      makeSchedule("washer", `${today}T08:00:00`, `${today}T09:00:00`),
    ];
    render(
      <ScheduleTimeline schedules={schedules} onSelectSchedule={onSelect} />,
    );
    fireEvent.click(screen.getByTestId("schedule-block-washer"));
    expect(onSelect).toHaveBeenCalledWith(schedules[0]);
  });

  it("renders price zone markers when priceZones provided", () => {
    const schedules = [
      makeSchedule("washer", `${today}T08:00:00`, `${today}T09:00:00`),
    ];
    const zones = [
      {
        start: `${today}T08:00:00`,
        end: `${today}T10:00:00`,
        type: "cheap" as const,
      },
    ];
    render(<ScheduleTimeline schedules={schedules} priceZones={zones} />);
    expect(screen.getByTestId("price-zone-cheap")).toBeInTheDocument();
  });

  it("shows savings amount when showSavings=true", () => {
    const schedules = [
      makeSchedule("washer", `${today}T08:00:00`, `${today}T09:00:00`, 25),
    ];
    render(<ScheduleTimeline schedules={schedules} showSavings />);
    expect(screen.getAllByText(/\$25.00/).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/components/ScheduleTimeline.test.tsx (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  const mockSchedules = [
    {
      applianceId: "1",
      applianceName: "Washing Machine",
      scheduledStart: "2026-02-06T02:00:00Z",
      scheduledEnd: "2026-02-06T04:00:00Z",
      estimatedCost: 0.45,
      savings: 0.15,
      reason: "Lowest price period",
    },
    {
      applianceId: "2",
      applianceName: "Dishwasher",
      scheduledStart: "2026-02-06T03:00:00Z",
      scheduledEnd: "2026-02-06T04:30:00Z",
      estimatedCost: 0.3,
      savings: 0.1,
      reason: "Off-peak pricing",
    },
    {
      applianceId: "3",
      applianceName: "EV Charger",
      scheduledStart: "2026-02-06T01:00:00Z",
      scheduledEnd: "2026-02-06T06:00:00Z",
      estimatedCost: 2.5,
      savings: 1.2,
      reason: "Night rate",
    },
  ];

  describe("ScheduleTimeline", () => {
    it("renders timeline with all scheduled appliances", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      expect(screen.getByText("Washing Machine")).toBeInTheDocument();
      expect(screen.getByText("Dishwasher")).toBeInTheDocument();
      expect(screen.getByText("EV Charger")).toBeInTheDocument();
    });

    it("displays time blocks for each schedule", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      expect(screen.getByTestId("schedule-block-1")).toBeInTheDocument();
      expect(screen.getByTestId("schedule-block-2")).toBeInTheDocument();
      expect(screen.getByTestId("schedule-block-3")).toBeInTheDocument();
    });

    it("shows schedule details on hover", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      const washingMachineBlock = screen.getByTestId("schedule-block-1");
      fireEvent.mouseEnter(washingMachineBlock);

      expect(screen.getByText(/lowest price period/i)).toBeInTheDocument();
      expect(screen.getByText(/0\.45/)).toBeInTheDocument();
    });

    it("hides schedule tooltip when mouse leaves the block", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      const block = screen.getByTestId("schedule-block-1");
      fireEvent.mouseEnter(block);

      expect(screen.getByText(/lowest price period/i)).toBeInTheDocument();

      fireEvent.mouseLeave(block);

      expect(
        screen.queryByText(/lowest price period/i),
      ).not.toBeInTheDocument();
    });

    it("shows tooltip with cost and savings on hover", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      fireEvent.mouseEnter(screen.getByTestId("schedule-block-1"));

      expect(screen.getByText(/\$0\.45/)).toBeInTheDocument();
      expect(screen.getByText(/\$0\.15/)).toBeInTheDocument();
    });

    it("displays total savings for all schedules", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      // Total savings: 0.15 + 0.10 + 1.20 = 1.45
      expect(screen.getByText(/1\.45/)).toBeInTheDocument();
    });

    it('shows the "Today\'s Schedule" heading', () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      expect(screen.getByText("Today's Schedule")).toBeInTheDocument();
    });

    it("shows 24-hour timeline by default with hour labels", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      expect(screen.getByText("00:00")).toBeInTheDocument();
      expect(screen.getByText("12:00")).toBeInTheDocument();
    });

    it("renders hour labels at 0, 3, 6 ... 24 intervals", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      const hourLabels = [
        "00:00",
        "03:00",
        "06:00",
        "09:00",
        "12:00",
        "15:00",
        "18:00",
        "21:00",
        "24:00",
      ];
      for (const label of hourLabels) {
        expect(screen.getByText(label)).toBeInTheDocument();
      }
    });

    it("highlights current time on timeline when showCurrentTime is true", () => {
      render(<ScheduleTimeline schedules={mockSchedules} showCurrentTime />);

      expect(screen.getByTestId("current-time-marker")).toBeInTheDocument();
    });

    it("does not render current time marker when showCurrentTime is false", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      expect(
        screen.queryByTestId("current-time-marker"),
      ).not.toBeInTheDocument();
    });

    it("shows price zones on the timeline", () => {
      const priceZones = [
        { start: "01:00", end: "06:00", type: "cheap" as const },
        { start: "17:00", end: "21:00", type: "expensive" as const },
      ];

      render(
        <ScheduleTimeline schedules={mockSchedules} priceZones={priceZones} />,
      );

      expect(screen.getByTestId("price-zone-cheap")).toBeInTheDocument();
      expect(screen.getByTestId("price-zone-expensive")).toBeInTheDocument();
    });

    it("renders moderate price zone when provided", () => {
      const priceZones = [
        { start: "09:00", end: "12:00", type: "moderate" as const },
      ];

      render(
        <ScheduleTimeline schedules={mockSchedules} priceZones={priceZones} />,
      );

      expect(screen.getByTestId("price-zone-moderate")).toBeInTheDocument();
    });

    it("handles empty schedules gracefully", () => {
      render(<ScheduleTimeline schedules={[]} />);

      expect(screen.getByText(/no scheduled activities/i)).toBeInTheDocument();
    });

    it("shows accessible role on the empty state element", () => {
      render(<ScheduleTimeline schedules={[]} />);

      expect(
        screen.getByRole("img", {
          name: /schedule timeline - no scheduled activities/i,
        }),
      ).toBeInTheDocument();
    });

    it("allows clicking on a schedule to invoke onSelectSchedule", () => {
      const onSelectSchedule = jest.fn();

      render(
        <ScheduleTimeline
          schedules={mockSchedules}
          onSelectSchedule={onSelectSchedule}
        />,
      );

      fireEvent.click(screen.getByTestId("schedule-block-1"));

      expect(onSelectSchedule).toHaveBeenCalledTimes(1);
      expect(onSelectSchedule).toHaveBeenCalledWith(mockSchedules[0]);
    });

    it("does not throw when clicking a block without onSelectSchedule", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      expect(() =>
        fireEvent.click(screen.getByTestId("schedule-block-1")),
      ).not.toThrow();
    });

    it("displays overlapping schedules in separate rows", () => {
      // Washing Machine (02:00-04:00) overlaps Dishwasher (03:00-04:30);
      // EV Charger (01:00-06:00) overlaps both. All three must still appear.
      render(<ScheduleTimeline schedules={mockSchedules} />);

      expect(screen.getByTestId("schedule-block-1")).toBeInTheDocument();
      expect(screen.getByTestId("schedule-block-2")).toBeInTheDocument();
      expect(screen.getByTestId("schedule-block-3")).toBeInTheDocument();
    });

    it("shows savings indicator on each block when showSavings is true", () => {
      render(<ScheduleTimeline schedules={mockSchedules} showSavings />);

      const block1 = screen.getByTestId("schedule-block-1");
      expect(within(block1).getByText(/save/i)).toBeInTheDocument();
    });

    it("shows savings amount in block when showSavings is true", () => {
      render(<ScheduleTimeline schedules={mockSchedules} showSavings />);

      const block1 = screen.getByTestId("schedule-block-1");
      expect(within(block1).getByText(/\$0\.15/)).toBeInTheDocument();
    });

    it("does not show savings text inside blocks when showSavings is false", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      const block1 = screen.getByTestId("schedule-block-1");
      expect(within(block1).queryByText(/save/i)).not.toBeInTheDocument();
    });

    it("is accessible with proper ARIA labels", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      expect(
        screen.getByRole("img", { name: /schedule timeline/i }),
      ).toBeInTheDocument();
    });

    it("aria-label on the timeline includes the schedule count", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      const timeline = screen.getByRole("img", { name: /schedule timeline/i });
      expect(timeline.getAttribute("aria-label")).toContain("3");
    });

    it("supports drag and drop: sets draggable attribute when allowReschedule is true", () => {
      render(
        <ScheduleTimeline
          schedules={mockSchedules}
          allowReschedule
          onReschedule={jest.fn()}
        />,
      );

      const block = screen.getByTestId("schedule-block-1");
      expect(block).toHaveAttribute("draggable", "true");
    });

    it("schedule blocks are not draggable when allowReschedule is false", () => {
      render(<ScheduleTimeline schedules={mockSchedules} />);

      const block = screen.getByTestId("schedule-block-1");
      expect(block).toHaveAttribute("draggable", "false");
    });

    it("renders a single schedule without error", () => {
      const singleSchedule = [mockSchedules[0]!];

      render(<ScheduleTimeline schedules={singleSchedule} />);

      expect(screen.getByText("Washing Machine")).toBeInTheDocument();
      expect(screen.getByTestId("schedule-block-1")).toBeInTheDocument();
    });
  });
}
