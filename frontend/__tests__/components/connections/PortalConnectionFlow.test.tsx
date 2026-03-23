import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PortalConnectionFlow } from "@/components/connections/PortalConnectionFlow";
import "@testing-library/jest-dom";

// Mock cn utility
jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

// Mock lucide-react icons
jest.mock("lucide-react", () => ({
  Globe: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-globe" {...props} />
  ),
  ArrowLeft: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-back" {...props} />
  ),
  Loader2: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-loader" {...props} />
  ),
  CheckCircle: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-checkcircle" {...props} />
  ),
  AlertCircle: (props: React.SVGAttributes<SVGElement>) => (
    <svg data-testid="icon-alertcircle" {...props} />
  ),
}));

const mockFetch = global.fetch as jest.Mock;

/** Create a proper Response-like mock object with status and headers */
function mockResponse(
  data: unknown,
  opts: { ok?: boolean; status?: number } = {},
) {
  const ok = opts.ok ?? true;
  const status = opts.status ?? (ok ? 200 : 400);
  return Promise.resolve({
    ok,
    status,
    statusText: ok ? "OK" : "Bad Request",
    headers: new Headers({ "content-type": "application/json" }),
    json: () => Promise.resolve(data),
  });
}

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

const mockPortalConnectionResponse = {
  connection_id: "conn-portal-1",
  supplier_id: "sup-1",
  portal_username: "testuser",
  portal_login_url: null,
  portal_scrape_status: "pending",
  portal_last_scraped_at: null,
};

const mockScrapeResponse = {
  connection_id: "conn-portal-1",
  status: "completed",
  rates_extracted: 5,
  error: null,
  scraped_at: "2026-03-10T12:00:00Z",
};

describe("PortalConnectionFlow", () => {
  const defaultProps = {
    onBack: jest.fn(),
    onSuccess: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockReset();

    // Default: supplier registry returns suppliers
    mockFetch.mockImplementation((url: string) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      return mockResponse({});
    });
  });

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  it("renders the form heading", async () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    expect(
      screen.getByRole("heading", { name: /connect utility portal/i }),
    ).toBeInTheDocument();
  });

  it("renders description text", () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    expect(
      screen.getByText(/log in to your utility provider website/i),
    ).toBeInTheDocument();
  });

  it("renders supplier dropdown label", () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    expect(screen.getByText("Utility Provider")).toBeInTheDocument();
  });

  it("loads and displays supplier options", async () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    expect(screen.getByText("United Illuminating")).toBeInTheDocument();
  });

  it("renders username input", () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    expect(screen.getByLabelText(/portal username/i)).toBeInTheDocument();
  });

  it("renders password input", () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    const passwordInput = screen.getByLabelText(/portal password/i);
    expect(passwordInput).toBeInTheDocument();
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("renders optional login URL input", () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    expect(screen.getByLabelText(/portal login url/i)).toBeInTheDocument();
  });

  it("renders consent checkbox", () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    expect(
      screen.getByText(/i consent to rateshift securely storing/i),
    ).toBeInTheDocument();
  });

  it("renders security notice", () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    expect(screen.getByText("Secure Portal Access")).toBeInTheDocument();
    expect(screen.getByText(/aes-256 encryption/i)).toBeInTheDocument();
  });

  it("renders submit button", () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    expect(
      screen.getByRole("button", { name: /connect utility portal/i }),
    ).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Validation
  // -----------------------------------------------------------------------

  it("submit button is disabled when no fields are filled", async () => {
    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const submitButton = screen.getByRole("button", {
      name: /connect utility portal/i,
    });
    expect(submitButton).toBeDisabled();
  });

  it("submit button is disabled when only supplier is selected", async () => {
    const user = userEvent.setup();
    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "sup-1");

    expect(
      screen.getByRole("button", { name: /connect utility portal/i }),
    ).toBeDisabled();
  });

  it("submit button is enabled when all required fields are filled", async () => {
    const user = userEvent.setup();
    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));

    expect(
      screen.getByRole("button", { name: /connect utility portal/i }),
    ).not.toBeDisabled();
  });

  it("shows validation errors when form is submitted empty", async () => {
    const user = userEvent.setup();
    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    // Force submit by enabling the button state temporarily -- instead
    // submit the form directly
    const form = document.querySelector("form")!;
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );

    await waitFor(() => {
      expect(
        screen.getByText("Please select a utility provider"),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("Username is required")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
    expect(
      screen.getByText("You must consent before connecting"),
    ).toBeInTheDocument();
  });

  it("clears validation error when user fills a field", async () => {
    const user = userEvent.setup();
    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    // Trigger validation errors
    const form = document.querySelector("form")!;
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );

    await waitFor(() => {
      expect(screen.getByText("Username is required")).toBeInTheDocument();
    });

    // Fill username -- error should clear
    await user.type(screen.getByLabelText(/portal username/i), "testuser");

    expect(screen.queryByText("Username is required")).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Successful submission
  // -----------------------------------------------------------------------

  it("shows success state after successful connection and scrape", async () => {
    const user = userEvent.setup();

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST" &&
        !url.includes("/scrape")
      ) {
        return mockResponse(mockPortalConnectionResponse);
      }
      if (
        typeof url === "string" &&
        url.includes("/scrape") &&
        options?.method === "POST"
      ) {
        return mockResponse(mockScrapeResponse);
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /portal connection created/i }),
      ).toBeInTheDocument();
    });

    expect(screen.getByText(/successfully extracted/i)).toBeInTheDocument();
    expect(screen.getByText(/5/)).toBeInTheDocument();
  });

  it("shows success state even when scrape fails", async () => {
    const user = userEvent.setup();

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST" &&
        !url.includes("/scrape")
      ) {
        return mockResponse(mockPortalConnectionResponse);
      }
      if (
        typeof url === "string" &&
        url.includes("/scrape") &&
        options?.method === "POST"
      ) {
        return mockResponse({ detail: "Scrape timeout" }, { ok: false });
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /portal connection created/i }),
      ).toBeInTheDocument();
    });

    // Should still show success, but with the retry message
    expect(
      screen.getByText(/scrape will be retried automatically/i),
    ).toBeInTheDocument();
  });

  it("calls onSuccess when Done button is clicked in success state", async () => {
    const user = userEvent.setup();

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST" &&
        !url.includes("/scrape")
      ) {
        return mockResponse(mockPortalConnectionResponse);
      }
      if (typeof url === "string" && url.includes("/scrape")) {
        return mockResponse(mockScrapeResponse);
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      expect(screen.getByText("Done")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Done"));
    expect(defaultProps.onSuccess).toHaveBeenCalled();
  });

  // -----------------------------------------------------------------------
  // Error handling
  // -----------------------------------------------------------------------

  it("shows error state when connection creation fails", async () => {
    const user = userEvent.setup();

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST"
      ) {
        return mockResponse({ detail: "Invalid credentials" }, { ok: false });
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /connection failed/i }),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
  });

  it("shows Try Again and Cancel buttons in error state", async () => {
    const user = userEvent.setup();

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST"
      ) {
        return mockResponse({ detail: "Server error" }, { ok: false });
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      expect(screen.getByText("Try Again")).toBeInTheDocument();
    });
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("returns to form when Try Again is clicked", async () => {
    const user = userEvent.setup();

    let callCount = 0;
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST"
      ) {
        callCount++;
        if (callCount === 1) {
          return mockResponse({ detail: "Temporary error" }, { ok: false });
        }
        return mockResponse(mockPortalConnectionResponse);
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      expect(screen.getByText("Try Again")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Try Again"));

    // Should be back at the form
    expect(
      screen.getByRole("heading", { name: /connect utility portal/i }),
    ).toBeInTheDocument();
  });

  it("calls onBack when Cancel is clicked in error state", async () => {
    const user = userEvent.setup();

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST"
      ) {
        return mockResponse({ detail: "Error" }, { ok: false });
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      expect(screen.getByText("Cancel")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Cancel"));
    expect(defaultProps.onBack).toHaveBeenCalled();
  });

  // -----------------------------------------------------------------------
  // API payload
  // -----------------------------------------------------------------------

  it("submits the correct payload to the portal API", async () => {
    const user = userEvent.setup();

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST" &&
        !url.includes("/scrape")
      ) {
        return mockResponse(mockPortalConnectionResponse);
      }
      if (typeof url === "string" && url.includes("/scrape")) {
        return mockResponse(mockScrapeResponse);
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "myuser");
    await user.type(screen.getByLabelText(/portal password/i), "mypass123");
    await user.type(
      screen.getByLabelText(/portal login url/i),
      "https://myutility.com/login",
    );
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      const postCalls = mockFetch.mock.calls.filter(
        ([url, opts]: [string, RequestInit?]) =>
          typeof url === "string" &&
          url.includes("/connections/portal") &&
          opts?.method === "POST" &&
          !url.includes("/scrape"),
      );
      expect(postCalls).toHaveLength(1);

      const body = JSON.parse(postCalls[0][1].body as string);
      expect(body.supplier_id).toBe("sup-1");
      expect(body.portal_username).toBe("myuser");
      expect(body.portal_password).toBe("mypass123");
      expect(body.portal_login_url).toBe("https://myutility.com/login");
      expect(body.consent_given).toBe(true);
    });
  });

  it("omits portal_login_url when not provided", async () => {
    const user = userEvent.setup();

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST" &&
        !url.includes("/scrape")
      ) {
        return mockResponse(mockPortalConnectionResponse);
      }
      if (typeof url === "string" && url.includes("/scrape")) {
        return mockResponse(mockScrapeResponse);
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "myuser");
    await user.type(screen.getByLabelText(/portal password/i), "mypass123");
    // Do NOT fill in the login URL
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      const postCalls = mockFetch.mock.calls.filter(
        ([url, opts]: [string, RequestInit?]) =>
          typeof url === "string" &&
          url.includes("/connections/portal") &&
          opts?.method === "POST" &&
          !url.includes("/scrape"),
      );
      expect(postCalls).toHaveLength(1);

      const body = JSON.parse(postCalls[0][1].body as string);
      expect(body.portal_login_url).toBeUndefined();
    });
  });

  // -----------------------------------------------------------------------
  // Loading state
  // -----------------------------------------------------------------------

  it("shows loading indicator during submission", async () => {
    const user = userEvent.setup();

    // Make the portal POST hang
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (typeof url === "string" && url.includes("/suppliers/registry")) {
        return mockResponse({ suppliers: mockSuppliers });
      }
      if (
        typeof url === "string" &&
        url.includes("/connections/portal") &&
        options?.method === "POST"
      ) {
        return new Promise(() => {}); // Never resolves
      }
      return mockResponse({});
    });

    render(<PortalConnectionFlow {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Eversource Energy")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole("combobox"), "sup-1");
    await user.type(screen.getByLabelText(/portal username/i), "testuser");
    await user.type(screen.getByLabelText(/portal password/i), "testpass");
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /connect utility portal/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByText("Creating portal connection..."),
      ).toBeInTheDocument();
    });
  });
});
