import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { Modal } from "@/components/ui/modal";

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));
jest.mock("@/components/ui/button", () => ({
  Button: (
    props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
      children: React.ReactNode;
      variant?: string;
    },
  ) => <button onClick={props.onClick}>{props.children}</button>,
}));
jest.mock("lucide-react", () => ({
  X: () => <svg data-testid="x-icon" />,
}));

describe("Modal", () => {
  it("renders nothing when open=false", () => {
    render(
      <Modal open={false} onClose={jest.fn()} title="Test Modal">
        content
      </Modal>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders the dialog when open=true", () => {
    render(
      <Modal open onClose={jest.fn()} title="Test Modal">
        content
      </Modal>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("displays the title", () => {
    render(<Modal open onClose={jest.fn()} title="My Title" />);
    expect(screen.getByText("My Title")).toBeInTheDocument();
  });

  it("displays the description when provided", () => {
    render(
      <Modal
        open
        onClose={jest.fn()}
        title="T"
        description="Some description"
      />,
    );
    expect(screen.getByText("Some description")).toBeInTheDocument();
  });

  it("renders children content", () => {
    render(
      <Modal open onClose={jest.fn()} title="T">
        <span>Modal body</span>
      </Modal>,
    );
    expect(screen.getByText("Modal body")).toBeInTheDocument();
  });

  it("calls onClose when the X button is clicked", () => {
    const onClose = jest.fn();
    render(<Modal open onClose={onClose} title="T" />);
    // Find close button by the X icon
    fireEvent.click(screen.getByTestId("x-icon").closest("button")!);
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onConfirm when confirm button is clicked", () => {
    const onConfirm = jest.fn();
    render(<Modal open onClose={jest.fn()} title="T" onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("calls onClose when cancel button is clicked", () => {
    const onClose = jest.fn();
    render(<Modal open onClose={onClose} title="T" onConfirm={jest.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when Escape key is pressed", () => {
    const onClose = jest.fn();
    render(<Modal open onClose={onClose} title="T" />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
