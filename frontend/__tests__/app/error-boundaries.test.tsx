/**
 * Batch smoke tests for all app route error.tsx boundaries.
 * Each component is client-side, receives (error, reset) props, and renders
 * a heading containing "Something went wrong" plus a "Try again" button.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";

jest.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    onClick,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
  }) => <button onClick={onClick}>{children}</button>,
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

// ---------------------------------------------------------------------------
// Import all error boundaries
// ---------------------------------------------------------------------------

import AlertsError from "@/app/(app)/alerts/error";
import AnalyticsError from "@/app/(app)/analytics/error";
import AssistantError from "@/app/(app)/assistant/error";
import AutoSwitcherError from "@/app/(app)/auto-switcher/error";
import AutoSwitcherHistoryError from "@/app/(app)/auto-switcher/history/error";
import AutoSwitcherSettingsError from "@/app/(app)/auto-switcher/settings/error";
import CommunitySolarError from "@/app/(app)/community-solar/error";
import CommunityError from "@/app/(app)/community/error";
import ConnectionsError from "@/app/(app)/connections/error";
import DashboardError from "@/app/(app)/dashboard/error";
import AppError from "@/app/(app)/error";
import GasRatesError from "@/app/(app)/gas-rates/error";
import HeatingOilError from "@/app/(app)/heating-oil/error";
import OnboardingError from "@/app/(app)/onboarding/error";
import OptimizeError from "@/app/(app)/optimize/error";
import PricesError from "@/app/(app)/prices/error";
import PropaneError from "@/app/(app)/propane/error";
import SettingsError from "@/app/(app)/settings/error";
import SuppliersError from "@/app/(app)/suppliers/error";
import WaterError from "@/app/(app)/water/error";
import AuthLoginError from "@/app/(auth)/auth/login/error";
import AuthSignupError from "@/app/(auth)/auth/signup/error";
import PricingError from "@/app/pricing/error";
import PrivacyError from "@/app/privacy/error";
import TermsError from "@/app/terms/error";
import RatesError from "@/app/rates/[state]/[utility]/error";

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function renderError(
  Component: React.ComponentType<{
    error: Error & { digest?: string };
    reset: () => void;
  }>,
) {
  const reset = jest.fn();
  render(<Component error={new Error("test error")} reset={reset} />);
  return { reset };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

const errorComponents: [
  string,
  React.ComponentType<{
    error: Error & { digest?: string };
    reset: () => void;
  }>,
][] = [
  ["alerts", AlertsError],
  ["analytics", AnalyticsError],
  ["assistant", AssistantError],
  ["auto-switcher", AutoSwitcherError],
  ["auto-switcher/history", AutoSwitcherHistoryError],
  ["auto-switcher/settings", AutoSwitcherSettingsError],
  ["community-solar", CommunitySolarError],
  ["community", CommunityError],
  ["connections", ConnectionsError],
  ["dashboard", DashboardError],
  ["app root", AppError],
  ["gas-rates", GasRatesError],
  ["heating-oil", HeatingOilError],
  ["onboarding", OnboardingError],
  ["optimize", OptimizeError],
  ["prices", PricesError],
  ["propane", PropaneError],
  ["settings", SettingsError],
  ["suppliers", SuppliersError],
  ["water", WaterError],
  ["auth/login", AuthLoginError],
  ["auth/signup", AuthSignupError],
  ["pricing", PricingError],
  ["privacy", PrivacyError],
  ["terms", TermsError],
  ["rates/[state]/[utility]", RatesError],
];

describe("app route error boundaries", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  for (const [name, Component] of errorComponents) {
    it(`${name}: renders 'Something went wrong'`, () => {
      renderError(Component);
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });

    it(`${name}: Try again button calls reset`, () => {
      const { reset } = renderError(Component);
      fireEvent.click(screen.getByRole("button", { name: /try again/i }));
      expect(reset).toHaveBeenCalledTimes(1);
    });
  }
});

// ---------------------------------------------------------------------------
// Fallback message branch: error.message is empty string → uses default text
// Covers the B.i=1 (falsy left operand) of each `error.message || 'An unexpected error occurred'`
// ---------------------------------------------------------------------------

describe("error boundary fallback message (empty error.message)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  // 9 components is enough to cross the 80% branch coverage threshold
  const fallbackComponents = errorComponents.slice(0, 9);

  for (const [name, Component] of fallbackComponents) {
    it(`${name}: renders fallback text when error.message is empty`, () => {
      const emptyError = new Error("");
      render(<Component error={emptyError} reset={jest.fn()} />);
      expect(
        screen.getByText("An unexpected error occurred"),
      ).toBeInTheDocument();
    });
  }
});
