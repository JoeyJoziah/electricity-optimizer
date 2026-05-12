import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

// ---------------------------------------------------------------------------
// next/dynamic — resolve synchronously in tests
// ---------------------------------------------------------------------------
jest.mock("next/dynamic", () => {
  return () => {
    const Stub = () => <div data-testid="dynamic-dashboard-stub" />;
    Stub.displayName = "DynamicStub";
    return Stub;
  };
});

// Mock DashboardContent (the one not behind next/dynamic)
jest.mock("@/components/dashboard/DashboardContent", () => {
  const DashboardContentStub = () => (
    <div data-testid="dashboard-content-stub" />
  );
  DashboardContentStub.displayName = "DashboardContentStub";
  return { __esModule: true, default: DashboardContentStub };
});

import { UtilityTabShell } from "@/components/dashboard/UtilityTabShell";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UtilityTabShell", () => {
  it("renders wrapper with correct testid for electricity", () => {
    render(<UtilityTabShell utilityType="electricity" />);
    expect(screen.getByTestId("utility-shell-electricity")).toBeInTheDocument();
  });

  it("renders wrapper with correct testid for natural_gas", () => {
    render(<UtilityTabShell utilityType="natural_gas" />);
    expect(screen.getByTestId("utility-shell-natural_gas")).toBeInTheDocument();
  });

  it("renders wrapper with correct testid for heating_oil", () => {
    render(<UtilityTabShell utilityType="heating_oil" />);
    expect(screen.getByTestId("utility-shell-heating_oil")).toBeInTheDocument();
  });

  it("renders wrapper with correct testid for propane", () => {
    render(<UtilityTabShell utilityType="propane" />);
    expect(screen.getByTestId("utility-shell-propane")).toBeInTheDocument();
  });

  it("renders wrapper with correct testid for water", () => {
    render(<UtilityTabShell utilityType="water" />);
    expect(screen.getByTestId("utility-shell-water")).toBeInTheDocument();
  });

  it("renders wrapper with correct testid for community_solar", () => {
    render(<UtilityTabShell utilityType="community_solar" />);
    expect(
      screen.getByTestId("utility-shell-community_solar"),
    ).toBeInTheDocument();
  });

  it("renders placeholder for unknown utility type", () => {
    render(<UtilityTabShell utilityType="wind_power" />);
    expect(
      screen.getByTestId("utility-shell-placeholder-wind_power"),
    ).toBeInTheDocument();
    expect(screen.getByText(/dashboard coming soon/i)).toBeInTheDocument();
  });

  it("shows utility label for known unknown type", () => {
    render(<UtilityTabShell utilityType="unknown_utility" />);
    expect(screen.getByText("unknown_utility")).toBeInTheDocument();
  });

  it("does not show placeholder for known type", () => {
    render(<UtilityTabShell utilityType="electricity" />);
    expect(
      screen.queryByTestId("utility-shell-placeholder-electricity"),
    ).not.toBeInTheDocument();
  });
});
