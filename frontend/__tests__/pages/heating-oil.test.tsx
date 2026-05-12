import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/components/heating-oil/HeatingOilDashboard", () => ({
  HeatingOilDashboard: () => <div data-testid="heating-oil-dashboard" />,
}));

import HeatingOilPage, { metadata } from "@/app/(app)/heating-oil/page";

describe("HeatingOilPage", () => {
  it("renders HeatingOilDashboard", () => {
    render(<HeatingOilPage />);
    expect(screen.getByTestId("heating-oil-dashboard")).toBeInTheDocument();
  });

  it('shows "Heating Oil Prices" heading', () => {
    render(<HeatingOilPage />);
    expect(
      screen.getByRole("heading", { name: /heating oil prices/i }),
    ).toBeInTheDocument();
  });

  it("has correct title metadata", () => {
    expect(metadata.title).toBe("Heating Oil Prices | RateShift");
  });
});
