import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/components/dashboard/DashboardTabs", () => ({
  __esModule: true,
  default: () => <div data-testid="dashboard-tabs" />,
}));

jest.mock("@/components/error-boundary", () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: () => <div data-testid="skeleton" />,
  ChartSkeleton: () => <div data-testid="chart-skeleton" />,
}));

import DashboardPage, { metadata } from "@/app/(app)/dashboard/page";

describe("DashboardPage", () => {
  it("renders DashboardTabs", () => {
    render(<DashboardPage />);
    expect(screen.getByTestId("dashboard-tabs")).toBeInTheDocument();
  });

  it("has correct title metadata", () => {
    expect(metadata.title).toBe("Dashboard | RateShift");
  });
});
