import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseSettingsStore = jest.fn();

jest.mock("@/lib/store/settings", () => ({
  useSettingsStore: (selector: (s: Record<string, unknown>) => unknown) =>
    mockUseSettingsStore(selector),
}));

// Stub child components to isolate AllUtilitiesTab logic
jest.mock("@/components/dashboard/CombinedSavingsCard", () => ({
  CombinedSavingsCard: () => <div data-testid="combined-savings-card-stub" />,
}));

jest.mock("@/components/dashboard/NeighborhoodCard", () => ({
  NeighborhoodCard: () => <div data-testid="neighborhood-card-stub" />,
}));

import { AllUtilitiesTab } from "@/components/dashboard/AllUtilitiesTab";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupStore(utilityTypes: string[]) {
  mockUseSettingsStore.mockImplementation(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ utilityTypes }),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AllUtilitiesTab", () => {
  beforeEach(() => {
    mockUseSettingsStore.mockReset();
  });

  it("renders the all-utilities-tab wrapper", () => {
    setupStore(["electricity"]);
    render(<AllUtilitiesTab />);
    expect(screen.getByTestId("all-utilities-tab")).toBeInTheDocument();
  });

  it("renders CombinedSavingsCard and NeighborhoodCard", () => {
    setupStore(["electricity"]);
    render(<AllUtilitiesTab />);
    expect(
      screen.getByTestId("combined-savings-card-stub"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("neighborhood-card-stub")).toBeInTheDocument();
  });

  it("renders a summary card for each user utility", () => {
    setupStore(["electricity", "natural_gas", "heating_oil"]);
    render(<AllUtilitiesTab />);
    expect(
      screen.getByTestId("utility-summary-electricity"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("utility-summary-natural_gas"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("utility-summary-heating_oil"),
    ).toBeInTheDocument();
  });

  it("renders correct label for electricity", () => {
    setupStore(["electricity"]);
    render(<AllUtilitiesTab />);
    expect(screen.getByText("Electricity")).toBeInTheDocument();
  });

  it("renders correct label for natural_gas", () => {
    setupStore(["natural_gas"]);
    render(<AllUtilitiesTab />);
    expect(screen.getByText("Natural Gas")).toBeInTheDocument();
  });

  it("renders correct label for community_solar", () => {
    setupStore(["community_solar"]);
    render(<AllUtilitiesTab />);
    expect(screen.getByText("Community Solar")).toBeInTheDocument();
  });

  it("falls back to utility_type key as label for unknown utility", () => {
    setupStore(["nuclear_power"]);
    render(<AllUtilitiesTab />);
    expect(screen.getByText("nuclear_power")).toBeInTheDocument();
  });

  it("renders no summary cards when utilityTypes is empty", () => {
    setupStore([]);
    render(<AllUtilitiesTab />);
    expect(screen.queryByTestId(/utility-summary-/)).not.toBeInTheDocument();
  });

  it("renders correct number of summary cards", () => {
    setupStore(["electricity", "water"]);
    render(<AllUtilitiesTab />);
    const cards = screen
      .getAllByTestId(/utility-summary-/)
      .filter((el) =>
        el.getAttribute("data-testid")?.startsWith("utility-summary-"),
      );
    expect(cards).toHaveLength(2);
  });
});
