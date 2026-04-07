import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

import {
  ForecastTeaser,
  SavingsTeaser,
} from "@/components/dashboard/TeaserCards";

describe("ForecastTeaser", () => {
  it("renders a blurred chart placeholder with visible time labels", () => {
    render(<ForecastTeaser />);

    // The blurred chart container should be present
    const blurredChart = screen.getByTestId("forecast-teaser-chart");
    expect(blurredChart).toBeInTheDocument();

    // Time labels on x-axis should be visible (not blurred)
    const timeLabels = screen.getByTestId("forecast-teaser-time-axis");
    expect(timeLabels).toBeInTheDocument();
  });

  it("renders the chart shape with blur applied to data", () => {
    render(<ForecastTeaser />);

    const blurredData = screen.getByTestId("forecast-teaser-blurred-data");
    expect(blurredData).toBeInTheDocument();
    // Verify blur filter is applied
    expect(blurredData).toHaveStyle({ filter: "blur(8px)" });
  });

  it("shows an overlay CTA below the blurred content", () => {
    render(<ForecastTeaser />);

    // The CTA should be present
    const cta = screen.getByTestId("forecast-teaser-cta");
    expect(cta).toBeInTheDocument();

    // CTA text should explain the value
    expect(
      screen.getByText(/upgrade to see exact forecasts/i),
    ).toBeInTheDocument();

    // CTA link should go to pricing
    const link = screen.getByRole("link", { name: /unlock forecasts/i });
    expect(link).toHaveAttribute("href", "/pricing");
  });

  it("has proper aria-label for accessibility on the blurred region", () => {
    render(<ForecastTeaser />);

    const blurredData = screen.getByTestId("forecast-teaser-blurred-data");
    expect(blurredData).toHaveAttribute("aria-label");
    expect(blurredData.getAttribute("aria-label")).toMatch(
      /forecast chart preview/i,
    );
  });

  it("renders the CTA with outline variant (not primary)", () => {
    render(<ForecastTeaser />);

    // The CTA button should use a low-pressure variant
    const button = screen.getByRole("link", { name: /unlock forecasts/i });
    expect(button).toBeInTheDocument();
    // It should NOT have the primary bg color class
    expect(button.className).not.toMatch(/bg-primary-600/);
  });
});

describe("SavingsTeaser", () => {
  it("renders a savings estimate range for a northeast region", () => {
    render(<SavingsTeaser region="us_ct" />);

    // Should show the dollar range prominently
    expect(screen.getByText(/\$200/)).toBeInTheDocument();
    expect(screen.getByText(/\$400/)).toBeInTheDocument();
    expect(screen.getByText(/year/i)).toBeInTheDocument();
  });

  it("renders a savings estimate range for a southeast region", () => {
    render(<SavingsTeaser region="us_fl" />);

    expect(screen.getByText(/\$150/)).toBeInTheDocument();
    expect(screen.getByText(/\$300/)).toBeInTheDocument();
  });

  it("renders a savings estimate range for a midwest region", () => {
    render(<SavingsTeaser region="us_oh" />);

    expect(screen.getByText(/\$160/)).toBeInTheDocument();
    expect(screen.getByText(/\$320/)).toBeInTheDocument();
  });

  it("renders a savings estimate range for a west region", () => {
    render(<SavingsTeaser region="us_ca" />);

    expect(screen.getByText(/\$180/)).toBeInTheDocument();
    expect(screen.getByText(/\$350/)).toBeInTheDocument();
  });

  it("renders a savings estimate range for a south central region", () => {
    render(<SavingsTeaser region="us_tx" />);

    expect(screen.getByText(/\$150/)).toBeInTheDocument();
    expect(screen.getByText(/\$300/)).toBeInTheDocument();
  });

  it("renders a fallback range when region is unknown", () => {
    render(<SavingsTeaser region="uk" />);

    // Should show a generic range
    expect(screen.getByText(/\$150/)).toBeInTheDocument();
    expect(screen.getByText(/\$350/)).toBeInTheDocument();
  });

  it("renders a fallback range when region is undefined", () => {
    render(<SavingsTeaser region={undefined} />);

    expect(screen.getByText(/\$150/)).toBeInTheDocument();
    expect(screen.getByText(/\$350/)).toBeInTheDocument();
  });

  it("shows a CTA below the savings range (not replacing it)", () => {
    render(<SavingsTeaser region="us_ct" />);

    // Range should be visible
    expect(screen.getByText(/\$200/)).toBeInTheDocument();

    // CTA should be below
    const cta = screen.getByTestId("savings-teaser-cta");
    expect(cta).toBeInTheDocument();
    expect(screen.getByText(/get exact savings with pro/i)).toBeInTheDocument();

    // CTA link should go to pricing
    const link = screen.getByRole("link", { name: /see exact savings/i });
    expect(link).toHaveAttribute("href", "/pricing");
  });

  it("uses green color for dollar amounts", () => {
    render(<SavingsTeaser region="us_ct" />);

    const rangeContainer = screen.getByTestId("savings-teaser-range");
    expect(rangeContainer).toBeInTheDocument();
    // The range should have success/green color classes
    expect(rangeContainer.className).toMatch(/text-success/);
  });

  it("has proper accessible labels", () => {
    render(<SavingsTeaser region="us_ct" />);

    const rangeContainer = screen.getByTestId("savings-teaser-range");
    expect(rangeContainer).toHaveAttribute("aria-label");
    expect(rangeContainer.getAttribute("aria-label")).toMatch(
      /estimated annual savings/i,
    );
  });
});
