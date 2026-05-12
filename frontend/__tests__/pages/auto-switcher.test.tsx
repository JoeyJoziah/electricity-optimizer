import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/components/auto-switcher/AutoSwitcherContent", () => ({
  __esModule: true,
  default: () => <div data-testid="auto-switcher-content" />,
}));

jest.mock(
  "./SwitchHistoryContent",
  () => ({
    __esModule: true,
    default: () => <div data-testid="switch-history-content" />,
  }),
  { virtual: true },
);

jest.mock(
  "./AutoSwitcherSettingsContent",
  () => ({
    __esModule: true,
    default: () => <div data-testid="auto-switcher-settings-content" />,
  }),
  { virtual: true },
);

import AutoSwitcherPage, { metadata } from "@/app/(app)/auto-switcher/page";

describe("AutoSwitcherPage", () => {
  it("renders AutoSwitcherContent", () => {
    render(<AutoSwitcherPage />);
    expect(screen.getByTestId("auto-switcher-content")).toBeInTheDocument();
  });

  it("has correct title metadata", () => {
    expect(metadata.title).toBe("Auto Switcher | RateShift");
  });
});
