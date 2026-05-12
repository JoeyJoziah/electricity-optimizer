/**
 * Batch smoke tests for all app route loading.tsx skeleton screens.
 * Each component renders without props and produces some DOM output.
 */
import { render } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({
    className,
    variant,
  }: {
    className?: string;
    variant?: string;
  }) => (
    <div data-testid="skeleton" data-variant={variant} className={className} />
  ),
  ChartSkeleton: ({ height }: { height?: number }) => (
    <div data-testid="chart-skeleton" style={{ height }} />
  ),
}));

import AlertsLoading from "@/app/(app)/alerts/loading";
import AnalyticsLoading from "@/app/(app)/analytics/loading";
import AssistantLoading from "@/app/(app)/assistant/loading";
import AutoSwitcherLoading from "@/app/(app)/auto-switcher/loading";
import AutoSwitcherHistoryLoading from "@/app/(app)/auto-switcher/history/loading";
import AutoSwitcherSettingsLoading from "@/app/(app)/auto-switcher/settings/loading";
import CommunitySolarLoading from "@/app/(app)/community-solar/loading";
import CommunityLoading from "@/app/(app)/community/loading";
import ConnectionsLoading from "@/app/(app)/connections/loading";
import DashboardLoading from "@/app/(app)/dashboard/loading";
import GasRatesLoading from "@/app/(app)/gas-rates/loading";
import HeatingOilLoading from "@/app/(app)/heating-oil/loading";
import OnboardingLoading from "@/app/(app)/onboarding/loading";
import OptimizeLoading from "@/app/(app)/optimize/loading";
import PricesLoading from "@/app/(app)/prices/loading";
import PropaneLoading from "@/app/(app)/propane/loading";
import SettingsLoading from "@/app/(app)/settings/loading";
import SuppliersLoading from "@/app/(app)/suppliers/loading";
import WaterLoading from "@/app/(app)/water/loading";
import AuthCallbackLoading from "@/app/(auth)/auth/callback/loading";
import AuthForgotPasswordLoading from "@/app/(auth)/auth/forgot-password/loading";
import AuthLoginLoading from "@/app/(auth)/auth/login/loading";
import AuthResetPasswordLoading from "@/app/(auth)/auth/reset-password/loading";
import AuthSignupLoading from "@/app/(auth)/auth/signup/loading";
import AuthVerifyEmailLoading from "@/app/(auth)/auth/verify-email/loading";
import ArchitectureLoading from "@/app/(dev)/architecture/loading";
import PricingLoading from "@/app/pricing/loading";
import PrivacyLoading from "@/app/privacy/loading";
import TermsLoading from "@/app/terms/loading";
import RatesLoading from "@/app/rates/[state]/[utility]/loading";

const loadingComponents: [string, React.ComponentType][] = [
  ["alerts", AlertsLoading],
  ["analytics", AnalyticsLoading],
  ["assistant", AssistantLoading],
  ["auto-switcher", AutoSwitcherLoading],
  ["auto-switcher/history", AutoSwitcherHistoryLoading],
  ["auto-switcher/settings", AutoSwitcherSettingsLoading],
  ["community-solar", CommunitySolarLoading],
  ["community", CommunityLoading],
  ["connections", ConnectionsLoading],
  ["dashboard", DashboardLoading],
  ["gas-rates", GasRatesLoading],
  ["heating-oil", HeatingOilLoading],
  ["onboarding", OnboardingLoading],
  ["optimize", OptimizeLoading],
  ["prices", PricesLoading],
  ["propane", PropaneLoading],
  ["settings", SettingsLoading],
  ["suppliers", SuppliersLoading],
  ["water", WaterLoading],
  ["auth/callback", AuthCallbackLoading],
  ["auth/forgot-password", AuthForgotPasswordLoading],
  ["auth/login", AuthLoginLoading],
  ["auth/reset-password", AuthResetPasswordLoading],
  ["auth/signup", AuthSignupLoading],
  ["auth/verify-email", AuthVerifyEmailLoading],
  ["dev/architecture", ArchitectureLoading],
  ["pricing", PricingLoading],
  ["privacy", PrivacyLoading],
  ["terms", TermsLoading],
  ["rates/[state]/[utility]", RatesLoading],
];

describe("app route loading skeletons", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  for (const [name, Component] of loadingComponents) {
    it(`${name}: renders without crashing`, () => {
      expect(() => render(<Component />)).not.toThrow();
    });
  }
});
