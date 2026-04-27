import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DirectLoginForm } from "@/components/connections/DirectLoginForm";
import "@testing-library/jest-dom";

// Mock cn utility
jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

// Mock lucide-react icons (includes Loader2 needed by Button component)
jest.mock("lucide-react", () => ({
  KeyRound: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-key" {...props} />
  ),
  ExternalLink: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-ext" {...props} />
  ),
  AlertCircle: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-alert" {...props} />
  ),
  CheckCircle2: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-check" {...props} />
  ),
  RefreshCw: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-refresh" {...props} />
  ),
  Clock: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-clock" {...props} />
  ),
  Zap: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-zap" {...props} />
  ),
  AlertTriangle: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-warn" {...props} />
  ),
  DollarSign: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-dollar" {...props} />
  ),
  Loader2: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-loader" {...props} />
  ),
}));

const mockFetch = global.fetch as jest.Mock;

const mockSuppliers = [
  {
    id: "sup-1",
    name: "Eversource Energy",
    region: "CT",
    utility_type: "electricity",
  },
  {
    id: "sup-2",
    name: "United Illuminating",
    region: "CT",
    utility_type: "electricity",
  },
];

describe("DirectLoginForm", () => {
  const defaultProps = {
    onComplete: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockReset();

    // Default: supplier registry returns suppliers
    mockFetch.mockImplementation((url: string) => {
      if (url.includes("/suppliers/registry")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suppliers: mockSuppliers }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  it("renders the form heading", async () => {
    render(<DirectLoginForm {...defaultProps} />);

    // findByRole awaits async state settling (loadSuppliers effect) before asserting
    expect(
      await screen.findByRole("heading", { name: /connect utility account/i }),
    ).toBeInTheDocument();
  });

  it("renders description text", async () => {
    render(<DirectLoginForm {...defaultProps} />);

    // Wait for supplier fetch to complete so the act() warning is suppressed
    await waitFor(() =>
      expect(
        screen.getByText(/link your provider account to automatically sync/i),
      ).toBeInTheDocument(),
    );
  });

  it("renders supplier dropdown label", async () => {
    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() =>
      expect(screen.getByText("Utility Provider")).toBeInTheDocument(),
    );
  });

  it("loads and displays supplier options", async () => {
    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    expect(screen.getByText("United Illuminating")).toBeInTheDocument();
  });

  it("displays UtilityAPI info panel", async () => {
    render(<DirectLoginForm {...defaultProps} />);

    expect(
      await screen.findByText("Powered by UtilityAPI"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/redirected to securely authorize read-only access/i),
    ).toBeInTheDocument();
  });

  it("renders consent checkbox", async () => {
    render(<DirectLoginForm {...defaultProps} />);

    // Label text uses the current "RateShift" brand name — not the old
    // "Electricity Optimizer" working name that was used before the rebrand.
    expect(
      await screen.findByText(/i consent to rateshift accessing/i),
    ).toBeInTheDocument();
  });

  it("submit button is disabled when no supplier selected and consent unchecked", async () => {
    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const submitButton = screen.getByRole("button", {
      name: /connect utility account/i,
    });
    expect(submitButton).toBeDisabled();
  });

  it("submit button is disabled when supplier selected but consent unchecked", async () => {
    const user = userEvent.setup();
    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "sup-1");

    const submitButton = screen.getByRole("button", {
      name: /connect utility account/i,
    });
    expect(submitButton).toBeDisabled();
  });

  it("submit button is disabled when consent checked but no supplier selected", async () => {
    const user = userEvent.setup();
    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const checkboxes = screen.getAllByRole("checkbox");
    for (const cb of checkboxes) {
      await user.click(cb);
    }

    const submitButton = screen.getByRole("button", {
      name: /connect utility account/i,
    });
    expect(submitButton).toBeDisabled();
  });

  it("submit button is disabled when only one consent checkbox is checked", async () => {
    const user = userEvent.setup();
    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "sup-1");

    // Only check the first consent checkbox
    const checkboxes = screen.getAllByRole("checkbox");
    await user.click(checkboxes[0]!);

    const submitButton = screen.getByRole("button", {
      name: /connect utility account/i,
    });
    expect(submitButton).toBeDisabled();
  });

  it("submit button is enabled when supplier is selected and both consents checked", async () => {
    const user = userEvent.setup();
    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "sup-1");

    const checkboxes = screen.getAllByRole("checkbox");
    for (const cb of checkboxes) {
      await user.click(cb);
    }

    const submitButton = screen.getByRole("button", {
      name: /connect utility account/i,
    });
    expect(submitButton).not.toBeDisabled();
  });

  it("shows error when submitted without supplier", async () => {
    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    // fireEvent.submit is wrapped in act() by RTL, avoiding the act() warning
    // that raw dispatchEvent triggers when it causes synchronous state updates.
    const form = document.querySelector("form")!;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(
        screen.getByText("Please select a utility provider"),
      ).toBeInTheDocument();
    });
  });

  it("submits form and calls API with correct payload", async () => {
    const user = userEvent.setup();
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes("/suppliers/registry")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suppliers: mockSuppliers }),
        });
      }
      if (
        url.includes("/connections/direct/authorize") &&
        options?.method === "POST"
      ) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ id: "new-conn-1", connection_id: "new-conn-1" }),
        });
      }
      // sync-status
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            last_sync_at: null,
            next_sync_at: null,
            last_sync_error: null,
            sync_frequency_hours: 6,
          }),
      });
    });

    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "sup-1");

    const checkboxes = screen.getAllByRole("checkbox");
    for (const cb of checkboxes) {
      await user.click(cb);
    }

    const submitButton = screen.getByRole("button", {
      name: /connect utility account/i,
    });
    await user.click(submitButton);

    await waitFor(() => {
      const postCalls = mockFetch.mock.calls.filter(
        ([url, opts]: [string, RequestInit?]) =>
          url.includes("/connections/direct/authorize") &&
          opts?.method === "POST",
      );
      expect(postCalls).toHaveLength(1);
      const body = JSON.parse(postCalls[0][1].body as string);
      expect(body.supplier_id).toBe("sup-1");
      expect(body.consent_given).toBe(true);
      expect(body.accept_addon_pricing).toBe(true);
    });
  });

  it("shows success state after connection is established", async () => {
    const user = userEvent.setup();
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes("/suppliers/registry")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suppliers: mockSuppliers }),
        });
      }
      if (
        url.includes("/connections/direct/authorize") &&
        options?.method === "POST"
      ) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: "new-conn-1" }),
        });
      }
      if (url.includes("/sync-status")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              last_sync_at: null,
              next_sync_at: null,
              last_sync_error: null,
              sync_frequency_hours: 6,
            }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "sup-1");
    for (const cb of screen.getAllByRole("checkbox")) {
      await user.click(cb);
    }
    await user.click(
      screen.getByRole("button", { name: /connect utility account/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /connection established/i }),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/your utility account is linked/i),
    ).toBeInTheDocument();
  });

  it("shows sync now and done buttons in success state", async () => {
    const user = userEvent.setup();
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes("/suppliers/registry")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suppliers: mockSuppliers }),
        });
      }
      if (
        url.includes("/connections/direct/authorize") &&
        options?.method === "POST"
      ) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: "new-conn-1" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            last_sync_at: null,
            next_sync_at: null,
            last_sync_error: null,
            sync_frequency_hours: 6,
          }),
      });
    });

    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    for (const cb of screen.getAllByRole("checkbox")) {
      await user.click(cb);
    }
    await user.click(
      screen.getByRole("button", { name: /connect utility account/i }),
    );

    await waitFor(() => {
      expect(screen.getByText(/sync now/i)).toBeInTheDocument();
    });
    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("shows 403 upgrade error message", async () => {
    const user = userEvent.setup();
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes("/suppliers/registry")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suppliers: mockSuppliers }),
        });
      }
      if (
        url.includes("/connections/direct/authorize") &&
        options?.method === "POST"
      ) {
        return Promise.resolve({
          ok: false,
          status: 403,
          json: () => Promise.resolve({ detail: "Upgrade required" }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "sup-1");
    for (const cb of screen.getAllByRole("checkbox")) {
      await user.click(cb);
    }
    await user.click(
      screen.getByRole("button", { name: /connect utility account/i }),
    );

    await waitFor(() => {
      expect(screen.getByText(/authentication required/i)).toBeInTheDocument();
    });
  });

  it("calls onComplete when Done button is clicked in success state", async () => {
    const user = userEvent.setup();
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes("/suppliers/registry")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suppliers: mockSuppliers }),
        });
      }
      if (
        url.includes("/connections/direct/authorize") &&
        options?.method === "POST"
      ) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: "new-conn-1" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            last_sync_at: null,
            next_sync_at: null,
            last_sync_error: null,
            sync_frequency_hours: 6,
          }),
      });
    });

    render(<DirectLoginForm {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "sup-1");
    for (const cb of screen.getAllByRole("checkbox")) {
      await user.click(cb);
    }
    await user.click(
      screen.getByRole("button", { name: /connect utility account/i }),
    );

    await waitFor(() => {
      expect(screen.getByText("Done")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Done"));
    expect(defaultProps.onComplete).toHaveBeenCalled();
  });
});
