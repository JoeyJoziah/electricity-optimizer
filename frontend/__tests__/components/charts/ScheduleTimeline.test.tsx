import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { ScheduleTimeline } from "@/components/charts/ScheduleTimeline";
import type { OptimizationSchedule } from "@/types";

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
