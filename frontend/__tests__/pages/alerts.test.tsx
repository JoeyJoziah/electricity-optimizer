import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/components/alerts/AlertsContent", () => ({
  __esModule: true,
  default: () => <div data-testid="alerts-content" />,
}));

import AlertsPage, { metadata } from "@/app/(app)/alerts/page";

describe("AlertsPage", () => {
  it("renders AlertsContent", () => {
    render(<AlertsPage />);
    expect(screen.getByTestId("alerts-content")).toBeInTheDocument();
  });

  it("has correct title metadata", () => {
    expect(metadata.title).toBe("Alerts | RateShift");
  });
});
