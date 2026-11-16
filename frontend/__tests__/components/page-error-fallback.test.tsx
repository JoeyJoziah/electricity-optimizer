import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { PageErrorFallback } from "@/components/page-error-fallback";

describe("PageErrorFallback", () => {
  it("renders the default heading", () => {
    render(<PageErrorFallback />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("renders the default message when no error prop", () => {
    render(<PageErrorFallback />);
    expect(
      screen.getByText(/an unexpected error occurred/i),
    ).toBeInTheDocument();
  });

  it("renders the error message when error prop is provided", () => {
    render(<PageErrorFallback error={new Error("Custom error message")} />);
    expect(screen.getByText("Custom error message")).toBeInTheDocument();
  });

  it("renders Go back button", () => {
    render(<PageErrorFallback />);
    expect(
      screen.getByRole("button", { name: /go back/i }),
    ).toBeInTheDocument();
  });

  it("renders Try again button", () => {
    render(<PageErrorFallback />);
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });

  it("calls onReset when Try again is clicked", () => {
    const onReset = jest.fn();
    render(<PageErrorFallback onReset={onReset} />);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("renders warning SVG icon", () => {
    render(<PageErrorFallback />);
    // Warning triangle icon rendered as SVG
    const svg = document.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });
});
