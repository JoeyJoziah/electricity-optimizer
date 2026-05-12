import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import GlobalError from "@/app/global-error";

describe("GlobalError", () => {
  it("renders the error heading", () => {
    render(<GlobalError error={new Error("boom")} reset={jest.fn()} />);
    expect(
      screen.getByRole("heading", { name: /something went wrong/i }),
    ).toBeInTheDocument();
  });

  it("shows critical error description", () => {
    render(<GlobalError error={new Error("boom")} reset={jest.fn()} />);
    expect(screen.getByText(/critical error/i)).toBeInTheDocument();
  });

  it("calls reset when Try again is clicked", () => {
    const reset = jest.fn();
    render(<GlobalError error={new Error("boom")} reset={reset} />);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("shows error digest when present", () => {
    const error = Object.assign(new Error("boom"), { digest: "abc123" });
    render(<GlobalError error={error} reset={jest.fn()} />);
    expect(screen.getByText(/Error ID: abc123/i)).toBeInTheDocument();
  });

  it("does not show error ID section when digest is absent", () => {
    render(<GlobalError error={new Error("boom")} reset={jest.fn()} />);
    expect(screen.queryByText(/error id/i)).not.toBeInTheDocument();
  });
});
