import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/components/water/WaterDashboard", () => ({
  WaterDashboard: () => <div data-testid="water-dashboard" />,
}));

import WaterPage, { metadata } from "@/app/(app)/water/page";

describe("WaterPage", () => {
  it("renders WaterDashboard", () => {
    render(<WaterPage />);
    expect(screen.getByTestId("water-dashboard")).toBeInTheDocument();
  });

  it('shows "Water Rates" heading', () => {
    render(<WaterPage />);
    expect(
      screen.getByRole("heading", { name: /water rates/i }),
    ).toBeInTheDocument();
  });

  it("has correct title metadata", () => {
    expect(metadata.title).toBe("Water Rates | RateShift");
  });
});
