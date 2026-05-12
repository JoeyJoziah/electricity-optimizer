import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/components/propane/PropaneDashboard", () => ({
  PropaneDashboard: () => <div data-testid="propane-dashboard" />,
}));

import PropanePage, { metadata } from "@/app/(app)/propane/page";

describe("PropanePage", () => {
  it("renders PropaneDashboard", () => {
    render(<PropanePage />);
    expect(screen.getByTestId("propane-dashboard")).toBeInTheDocument();
  });

  it('shows "Propane Prices" heading', () => {
    render(<PropanePage />);
    expect(
      screen.getByRole("heading", { name: /propane prices/i }),
    ).toBeInTheDocument();
  });

  it("has correct title metadata", () => {
    expect(metadata.title).toBe("Propane Prices | RateShift");
  });
});
