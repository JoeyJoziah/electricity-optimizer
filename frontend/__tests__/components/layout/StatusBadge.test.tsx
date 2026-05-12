import { render, screen } from "@testing-library/react";
import React from "react";
import { StatusBadge } from "@/components/layout/StatusBadge";

describe("StatusBadge", () => {
  it("renders null when statusPageUrl is empty", () => {
    const { container } = render(<StatusBadge statusPageUrl="" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a link when statusPageUrl is provided", () => {
    render(<StatusBadge statusPageUrl="https://status.example.com" />);
    const link = screen.getByRole("link");
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "https://status.example.com");
  });

  it("opens in a new tab with safe rel", () => {
    render(<StatusBadge statusPageUrl="https://status.example.com" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it('shows "System Status" text', () => {
    render(<StatusBadge statusPageUrl="https://status.example.com" />);
    expect(screen.getByText("System Status")).toBeInTheDocument();
  });
});
