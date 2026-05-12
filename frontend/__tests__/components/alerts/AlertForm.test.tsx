import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import React from "react";

// Mock Next.js Link
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

// Mock useCreateAlert hook
const mockMutate = jest.fn();
const mockMutation = {
  mutate: mockMutate,
  isPending: false,
  isError: false,
  error: null,
};

jest.mock("@/lib/hooks/useAlerts", () => ({
  useCreateAlert: () => mockMutation,
}));

// Import after mocks
import { AlertForm } from "@/components/alerts/AlertForm";
import { ApiClientError } from "@/lib/api/client";

function renderAlertForm(onSuccess = jest.fn()) {
  return render(<AlertForm onSuccess={onSuccess} />);
}

describe("AlertForm", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.assign(mockMutation, {
      mutate: mockMutate,
      isPending: false,
      isError: false,
      error: null,
    });
  });

  describe("rendering", () => {
    it("renders the form element with testid", () => {
      renderAlertForm();
      expect(screen.getByTestId("alert-form")).toBeInTheDocument();
    });

    it("renders region selector with default empty option", () => {
      renderAlertForm();
      expect(screen.getByTestId("region-select")).toHaveValue("");
    });

    it("renders submit button with label 'Create Alert'", () => {
      renderAlertForm();
      expect(screen.getByTestId("submit-alert")).toHaveTextContent(
        "Create Alert",
      );
    });

    it("optimal windows checkbox is checked by default", () => {
      renderAlertForm();
      expect(
        screen.getByRole("checkbox", {
          name: /notify me about optimal usage windows/i,
        }),
      ).toBeChecked();
    });
  });

  describe("validation", () => {
    it("shows 'Please select a region' error when no region is selected", async () => {
      const user = userEvent.setup();
      renderAlertForm();
      await user.click(screen.getByTestId("submit-alert"));
      expect(screen.getByTestId("form-error")).toHaveTextContent(
        "Please select a region.",
      );
    });

    it("shows 'At least one condition required' when no thresholds and no optimal windows", async () => {
      const user = userEvent.setup();
      renderAlertForm();
      // Select a region
      await user.selectOptions(screen.getByTestId("region-select"), "us_ct");
      // Uncheck optimal windows
      await user.click(
        screen.getByRole("checkbox", {
          name: /notify me about optimal usage windows/i,
        }),
      );
      await user.click(screen.getByTestId("submit-alert"));
      expect(screen.getByTestId("form-error")).toHaveTextContent(
        "At least one condition is required",
      );
    });

    it("shows error for non-positive price_below", async () => {
      renderAlertForm();
      await userEvent
        .setup()
        .selectOptions(screen.getByTestId("region-select"), "us_ct");
      // Simulate a zero value directly in the price_below state via the form submit
      // with priceBelow="-0.1" by firing a submit with the input set to that value.
      const form = screen.getByTestId("alert-form");
      const belowInput = form.querySelector(
        "input[id='price-below']",
      ) as HTMLInputElement;
      Object.defineProperty(belowInput, "value", {
        get: () => "-0.1",
        configurable: true,
      });
      fireEvent.change(belowInput, { target: { value: "-0.1" } });
      fireEvent.submit(form);
      expect(screen.getByTestId("form-error")).toHaveTextContent(
        "Price below must be a positive number.",
      );
    });

    it("shows error for non-positive price_above", async () => {
      renderAlertForm();
      await userEvent
        .setup()
        .selectOptions(screen.getByTestId("region-select"), "us_ct");
      const form = screen.getByTestId("alert-form");
      const aboveInput = form.querySelector(
        "input[id='price-above']",
      ) as HTMLInputElement;
      Object.defineProperty(aboveInput, "value", {
        get: () => "0",
        configurable: true,
      });
      fireEvent.change(aboveInput, { target: { value: "0" } });
      fireEvent.submit(form);
      expect(screen.getByTestId("form-error")).toHaveTextContent(
        "Price above must be a positive number.",
      );
    });
  });

  describe("valid submission", () => {
    it("calls createMutation.mutate with correct payload on valid submit", async () => {
      const user = userEvent.setup();
      renderAlertForm();
      await user.selectOptions(screen.getByTestId("region-select"), "us_ct");
      await user.type(screen.getByLabelText(/price below/i), "0.20");
      await user.click(screen.getByTestId("submit-alert"));

      expect(mockMutate).toHaveBeenCalledWith(
        {
          region: "us_ct",
          price_below: 0.2,
          price_above: null,
          notify_optimal_windows: true,
        },
        expect.any(Object),
      );
    });

    it("submits with only optimal windows checked (no price thresholds)", async () => {
      const user = userEvent.setup();
      renderAlertForm();
      await user.selectOptions(screen.getByTestId("region-select"), "us_ny");
      await user.click(screen.getByTestId("submit-alert"));

      expect(mockMutate).toHaveBeenCalledWith(
        {
          region: "us_ny",
          price_below: null,
          price_above: null,
          notify_optimal_windows: true,
        },
        expect.any(Object),
      );
    });
  });

  describe("loading state", () => {
    it("shows 'Creating...' and disables button while mutation is pending", () => {
      Object.assign(mockMutation, { isPending: true });
      renderAlertForm();
      const btn = screen.getByTestId("submit-alert");
      expect(btn).toHaveTextContent("Creating...");
      expect(btn).toBeDisabled();
    });
  });

  describe("error states", () => {
    it("shows tier limit error with upgrade link on 403", () => {
      const tierError = new ApiClientError({
        message: "Free plan limit",
        status: 403,
      });
      Object.assign(mockMutation, { isError: true, error: tierError });
      renderAlertForm();
      expect(screen.getByTestId("tier-limit-error")).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /upgrade to pro/i }),
      ).toHaveAttribute("href", "/pricing");
    });

    it("shows generic error message on non-403 error", () => {
      const genericError = new ApiClientError({
        message: "Server error",
        status: 500,
      });
      Object.assign(mockMutation, { isError: true, error: genericError });
      renderAlertForm();
      expect(screen.queryByTestId("tier-limit-error")).not.toBeInTheDocument();
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
