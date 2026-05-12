import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/components/analytics/AnalyticsDashboard", () => ({
  AnalyticsDashboard: () => <div data-testid="analytics-dashboard" />,
}));

jest.mock("@/components/error-boundary", () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

import AnalyticsPage, { metadata } from "@/app/(app)/analytics/page";

describe("AnalyticsPage", () => {
  it("renders AnalyticsDashboard", () => {
    render(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-dashboard")).toBeInTheDocument();
  });

  it('shows "Premium Analytics" heading', () => {
    render(<AnalyticsPage />);
    expect(screen.getByText("Premium Analytics")).toBeInTheDocument();
  });

  it("has correct title metadata", () => {
    expect(metadata.title).toBe("Premium Analytics | RateShift");
  });
});
