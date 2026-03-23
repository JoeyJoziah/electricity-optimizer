import { render, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";
import { Modal } from "@/components/ui/modal";
import "@testing-library/jest-dom";

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

jest.mock("lucide-react", () => ({
  X: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="x-icon" {...props} />
  ),
  Loader2: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="loader-icon" {...props} />
  ),
}));

describe("Modal focus trap a11y", () => {
  it("has no accessibility violations when open", async () => {
    const { container } = render(
      <Modal open={true} onClose={jest.fn()} title="Confirm action">
        <p>Are you sure you want to proceed?</p>
      </Modal>,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("closes on Escape key press", () => {
    const onClose = jest.fn();
    render(
      <Modal open={true} onClose={onClose} title="Test modal">
        <button>Action</button>
      </Modal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('has role="dialog" and aria-modal="true"', () => {
    const { container } = render(
      <Modal open={true} onClose={jest.fn()} title="Accessible modal" />,
    );
    const dialog = container.querySelector('[role="dialog"]');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // aria-labelledby uses a unique ID per modal instance (useId)
    const labelledBy = dialog?.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    const titleEl = container.querySelector(`#${CSS.escape(labelledBy!)}`);
    expect(titleEl).toBeInTheDocument();
  });

  it("modal title is linked via aria-labelledby", () => {
    const { container } = render(
      <Modal open={true} onClose={jest.fn()} title="Delete account" />,
    );
    const dialog = container.querySelector('[role="dialog"]');
    const titleId = dialog?.getAttribute("aria-labelledby");
    expect(titleId).toBeTruthy();
    const title = container.querySelector(`#${CSS.escape(titleId!)}`);
    expect(title).toBeInTheDocument();
    expect(title).toHaveTextContent("Delete account");
  });

  it("close button has accessible label", () => {
    const { getByRole } = render(
      <Modal open={true} onClose={jest.fn()} title="My modal" />,
    );
    const closeBtn = getByRole("button", { name: /close/i });
    expect(closeBtn).toBeInTheDocument();
  });

  it("has no accessibility violations with confirm/cancel buttons", async () => {
    const { container } = render(
      <Modal
        open={true}
        onClose={jest.fn()}
        title="Remove connection"
        description="This will disconnect your utility account."
        confirmLabel="Remove"
        cancelLabel="Keep connection"
        onConfirm={jest.fn()}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("has no accessibility violations with danger variant", async () => {
    const { container } = render(
      <Modal
        open={true}
        onClose={jest.fn()}
        title="Delete all data"
        description="This action is irreversible."
        confirmLabel="Delete permanently"
        onConfirm={jest.fn()}
        variant="danger"
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("renders nothing when closed and has no violations", async () => {
    const { container } = render(
      <Modal open={false} onClose={jest.fn()} title="Hidden modal" />,
    );
    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("generates unique IDs for multiple modal instances", () => {
    const { container } = render(
      <>
        <Modal open={true} onClose={jest.fn()} title="Modal A" />
        <Modal open={true} onClose={jest.fn()} title="Modal B" />
      </>,
    );
    const dialogs = container.querySelectorAll('[role="dialog"]');
    expect(dialogs).toHaveLength(2);
    const idA = dialogs[0].getAttribute("aria-labelledby");
    const idB = dialogs[1].getAttribute("aria-labelledby");
    expect(idA).not.toEqual(idB);
  });

  it("links aria-describedby to description element when provided", () => {
    const { container } = render(
      <Modal
        open={true}
        onClose={jest.fn()}
        title="Test"
        description="Some helpful description"
      />,
    );
    const dialog = container.querySelector('[role="dialog"]');
    const describedBy = dialog?.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const descEl = container.querySelector(`#${CSS.escape(describedBy!)}`);
    expect(descEl).toBeInTheDocument();
    expect(descEl).toHaveTextContent("Some helpful description");
  });

  it("does not set aria-describedby when no description is provided", () => {
    const { container } = render(
      <Modal open={true} onClose={jest.fn()} title="No desc" />,
    );
    const dialog = container.querySelector('[role="dialog"]');
    expect(dialog?.getAttribute("aria-describedby")).toBeNull();
  });
});
