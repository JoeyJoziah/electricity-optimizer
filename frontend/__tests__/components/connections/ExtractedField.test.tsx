import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { Zap, DollarSign } from "lucide-react";

import { ExtractedField } from "@/components/connections/ExtractedField";

describe("ExtractedField", () => {
  it("renders the label", () => {
    render(<ExtractedField icon={Zap} label="Rate" value="14.50 c/kWh" />);
    expect(screen.getByText("Rate")).toBeInTheDocument();
  });

  it("renders the value", () => {
    render(<ExtractedField icon={Zap} label="Rate" value="14.50 c/kWh" />);
    expect(screen.getByText("14.50 c/kWh")).toBeInTheDocument();
  });

  it("applies highlight border class when highlight=true", () => {
    const { container } = render(
      <ExtractedField icon={Zap} label="Rate" value="14.50 c/kWh" highlight />,
    );
    expect(container.firstChild).toHaveClass("border-primary-200");
  });

  it("applies non-highlight border class when highlight=false", () => {
    const { container } = render(
      <ExtractedField icon={Zap} label="Rate" value="14.50 c/kWh" />,
    );
    expect(container.firstChild).toHaveClass("border-gray-200");
  });

  it("renders an SVG icon from the passed icon prop", () => {
    const { container } = render(
      <ExtractedField icon={DollarSign} label="Amount" value="$123.45" />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("defaults highlight to false (no highlight classes)", () => {
    const { container } = render(
      <ExtractedField icon={Zap} label="Usage" value="850 kWh" />,
    );
    expect(container.firstChild).not.toHaveClass("border-primary-200");
    expect(container.firstChild).toHaveClass("border-gray-200");
  });
});
