import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

import { Toast } from "@/components/ui/toast";

describe("Toast", () => {
  const defaultProps = {
    id: "toast-1",
    variant: "success" as const,
    title: "Operation succeeded",
    onDismiss: jest.fn(),
  };

  beforeEach(() => {
    defaultProps.onDismiss.mockReset();
  });

  it("renders with role=alert", () => {
    render(<Toast {...defaultProps} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders the title", () => {
    render(<Toast {...defaultProps} />);
    expect(screen.getByText("Operation succeeded")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(<Toast {...defaultProps} description="All changes saved." />);
    expect(screen.getByText("All changes saved.")).toBeInTheDocument();
  });

  it("omits description paragraph when not provided", () => {
    render(<Toast {...defaultProps} />);
    expect(screen.queryByText(/all changes/i)).not.toBeInTheDocument();
  });

  it("renders dismiss button", () => {
    render(<Toast {...defaultProps} />);
    expect(
      screen.getByRole("button", { name: /dismiss notification/i }),
    ).toBeInTheDocument();
  });

  it("calls onDismiss with id when dismiss button is clicked", () => {
    const onDismiss = jest.fn();
    render(<Toast {...defaultProps} id="toast-99" onDismiss={onDismiss} />);
    fireEvent.click(
      screen.getByRole("button", { name: /dismiss notification/i }),
    );
    expect(onDismiss).toHaveBeenCalledWith("toast-99");
  });

  it("renders success variant", () => {
    const { container } = render(<Toast {...defaultProps} variant="success" />);
    expect(container.firstChild).toHaveClass("bg-success-50");
  });

  it("renders error variant", () => {
    const { container } = render(<Toast {...defaultProps} variant="error" />);
    expect(container.firstChild).toHaveClass("bg-danger-50");
  });

  it("renders warning variant", () => {
    const { container } = render(<Toast {...defaultProps} variant="warning" />);
    expect(container.firstChild).toHaveClass("bg-warning-50");
  });

  it("renders info variant", () => {
    const { container } = render(<Toast {...defaultProps} variant="info" />);
    expect(container.firstChild).toHaveClass("bg-primary-50");
  });
});
