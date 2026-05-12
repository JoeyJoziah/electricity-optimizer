import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { DashboardSchedule } from "@/components/dashboard/DashboardSchedule";

describe("DashboardSchedule", () => {
  it("renders the Today's Schedule heading", () => {
    render(<DashboardSchedule />);
    expect(screen.getByText("Today's Schedule")).toBeInTheDocument();
  });

  it("renders the empty-state prompt", () => {
    render(<DashboardSchedule />);
    expect(
      screen.getByText(/no optimization schedule set/i),
    ).toBeInTheDocument();
  });

  it("mentions appliances configuration in the empty state", () => {
    render(<DashboardSchedule />);
    expect(
      screen.getByText(/configure appliances in settings/i),
    ).toBeInTheDocument();
  });
});
