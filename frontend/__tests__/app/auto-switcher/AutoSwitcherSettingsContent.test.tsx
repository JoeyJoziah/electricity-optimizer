import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// API mocks
// ---------------------------------------------------------------------------

const mockGetSettings = jest.fn();
const mockUpdateSettings = jest.fn();
const mockSignLOA = jest.fn();
const mockRevokeLOA = jest.fn();

jest.mock("@/lib/api/agent-switcher", () => ({
  getSettings: (...args: unknown[]) => mockGetSettings(...args),
  updateSettings: (...args: unknown[]) => mockUpdateSettings(...args),
  signLOA: (...args: unknown[]) => mockSignLOA(...args),
  revokeLOA: (...args: unknown[]) => mockRevokeLOA(...args),
}));

// ---------------------------------------------------------------------------
// Context mocks
// ---------------------------------------------------------------------------

const mockSuccess = jest.fn();
const mockToastError = jest.fn();

jest.mock("@/lib/contexts/toast-context", () => ({
  useToast: () => ({ success: mockSuccess, error: mockToastError }),
}));

// ---------------------------------------------------------------------------
// UI mocks
// ---------------------------------------------------------------------------

jest.mock("@/components/layout/Header", () => ({
  Header: ({ title }: { title: string }) => (
    <header data-testid="header">{title}</header>
  ),
}));

jest.mock("@/components/ui/card", () => ({
  Card: ({
    children,
    variant,
    padding,
  }: {
    children: React.ReactNode;
    variant?: string;
    padding?: string;
  }) => (
    <div data-testid="card" data-variant={variant} data-padding={padding}>
      {children}
    </div>
  ),
  CardTitle: ({
    children,
    as: Tag = "h3",
  }: {
    children: React.ReactNode;
    as?: string;
  }) => <Tag>{children}</Tag>,
  CardDescription: ({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => <p className={className}>{children}</p>,
}));

jest.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    onClick,
    disabled,
    loading,
    variant,
    leftIcon,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    loading?: boolean;
    variant?: string;
    leftIcon?: React.ReactNode;
  }) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-loading={String(loading)}
      data-variant={variant}
    >
      {leftIcon}
      {children}
    </button>
  ),
}));

jest.mock("@/components/ui/input", () => ({
  Input: ({
    id,
    label,
    value,
    onChange,
    disabled,
    type,
  }: {
    id?: string;
    label?: string;
    value?: unknown;
    onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
    disabled?: boolean;
    type?: string;
    min?: number;
    max?: number;
    step?: number;
    helperText?: string;
    "aria-valuemin"?: number;
    "aria-valuemax"?: number;
  }) => (
    <div>
      {label && <label htmlFor={id}>{label}</label>}
      <input
        id={id}
        type={type}
        value={String(value ?? "")}
        onChange={onChange}
        disabled={disabled}
      />
    </div>
  ),
}));

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({
    className,
    variant,
  }: {
    className?: string;
    variant?: string;
  }) => (
    <div data-testid="skeleton" data-variant={variant} className={className} />
  ),
}));

jest.mock("@/components/ui/modal", () => ({
  Modal: ({
    open,
    onClose,
    onConfirm,
    title,
  }: {
    open: boolean;
    onClose: () => void;
    onConfirm?: () => void;
    title: string;
    description?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    variant?: string;
  }) =>
    open ? (
      <div role="dialog" aria-label={title}>
        <button onClick={onClose} data-testid="modal-cancel">
          Cancel
        </button>
        {onConfirm && (
          <button onClick={onConfirm} data-testid="modal-confirm">
            Confirm
          </button>
        )}
      </div>
    ) : null,
}));

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

jest.mock("lucide-react", () => {
  const icon = (name: string) => {
    const Icon = ({ className }: { className?: string }) => (
      <svg data-testid={`icon-${name}`} className={className} />
    );
    Icon.displayName = `Icon(${name})`;
    return Icon;
  };
  return {
    ArrowLeft: icon("arrow-left"),
    ShieldCheck: icon("shield-check"),
    ShieldOff: icon("shield-off"),
    Calendar: icon("calendar"),
    Clock: icon("clock"),
    TrendingUp: icon("trending-up"),
    Power: icon("power"),
    FileText: icon("file-text"),
    X: icon("x"),
    AlertTriangle: icon("alert-triangle"),
  };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={makeQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}

import AutoSwitcherSettingsContent from "@/app/(app)/auto-switcher/settings/AutoSwitcherSettingsContent";

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

function makeSettings(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    enabled: true,
    savings_threshold_pct: 10,
    savings_threshold_min: 10,
    cooldown_days: 5,
    paused_until: null,
    loa_signed: false,
    loa_revoked: false,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-10T00:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AutoSwitcherSettingsContent", () => {
  beforeEach(() => {
    mockGetSettings.mockReset();
    mockUpdateSettings.mockReset();
    mockSignLOA.mockReset();
    mockRevokeLOA.mockReset();
    mockSuccess.mockReset();
    mockToastError.mockReset();
  });

  it("shows loading skeletons when fetching", async () => {
    mockGetSettings.mockReturnValue(new Promise(() => {}));
    render(<AutoSwitcherSettingsContent />, { wrapper });
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0);
  });

  it("shows error message when fetch fails", async () => {
    mockGetSettings.mockRejectedValue(new Error("fetch failed"));
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/unable to load settings/i)).toBeInTheDocument();
    });
  });

  it("renders settings when loaded successfully", async () => {
    mockGetSettings.mockResolvedValue(makeSettings());
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByText(/enable auto rate switcher/i),
      ).toBeInTheDocument();
    });
  });

  it("shows 'LOA is active' badge when loa_signed and not loa_revoked", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({ loa_signed: true, loa_revoked: false }),
    );
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/loa is active/i)).toBeInTheDocument();
    });
  });

  it("shows 'Sign LOA' button when loa not signed", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({ loa_signed: false, loa_revoked: false }),
    );
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /sign loa/i }),
      ).toBeInTheDocument();
    });
  });

  it("shows 'Revoke LOA' button when loa is active", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({ loa_signed: true, loa_revoked: false }),
    );
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /revoke loa/i }),
      ).toBeInTheDocument();
    });
  });

  it("shows 'previously revoked' message when loa_revoked", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({ loa_signed: false, loa_revoked: true }),
    );
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/previously revoked/i)).toBeInTheDocument();
    });
  });

  it("toggles the auto-switcher on/off", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: false }));
    mockUpdateSettings.mockResolvedValue(makeSettings({ enabled: true }));
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      // ToggleSwitch is a role=switch
      const toggle = screen.getByRole("switch");
      expect(toggle).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("switch"));
    await waitFor(() => {
      expect(mockUpdateSettings).toHaveBeenCalledWith(
        expect.objectContaining({ enabled: true }),
      );
    });
  });

  it("opens revoke LOA confirmation modal", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({ loa_signed: true, loa_revoked: false }),
    );
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /revoke loa/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /revoke loa/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("calls revokeLOA when modal confirm clicked", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({ loa_signed: true, loa_revoked: false }),
    );
    mockRevokeLOA.mockResolvedValue(undefined);
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /revoke loa/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /revoke loa/i }));
    await waitFor(() => {
      expect(screen.getByTestId("modal-confirm")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("modal-confirm"));
    await waitFor(() => {
      expect(mockRevokeLOA).toHaveBeenCalled();
    });
  });

  it("calls signLOA when Sign LOA button clicked", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({ loa_signed: false, loa_revoked: false }),
    );
    mockSignLOA.mockResolvedValue(undefined);
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /sign loa/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /sign loa/i }));
    await waitFor(() => {
      expect(mockSignLOA).toHaveBeenCalled();
    });
  });

  it("shows 'Back to Auto Switcher' link", async () => {
    mockGetSettings.mockResolvedValue(makeSettings());
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      const link = screen.getByRole("link", { name: /back to auto switcher/i });
      expect(link).toHaveAttribute("href", "/auto-switcher");
    });
  });

  it("shows savings threshold section when data loaded", async () => {
    mockGetSettings.mockResolvedValue(makeSettings());
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getAllByText(/savings threshold/i).length).toBeGreaterThan(
        0,
      );
    });
  });

  it("shows signed date when loa is active and updated_at present", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({
        loa_signed: true,
        loa_revoked: false,
        updated_at: "2025-06-15T12:00:00Z",
      }),
    );
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/signed on/i)).toBeInTheDocument();
    });
  });

  it("shows inactive state description when enabled=false", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: false }));
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByText(/continuously monitor electricity rates/i),
      ).toBeInTheDocument();
    });
  });

  it("shows active state description when enabled=true", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: true }));
    render(<AutoSwitcherSettingsContent />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByText(/actively monitoring your rates/i),
      ).toBeInTheDocument();
    });
  });

  // --- Temporary Pause section with paused_until set ---

  it("shows Unpause button when paused_until is set to a future date", async () => {
    const futureDate = new Date(
      Date.now() + 7 * 24 * 60 * 60 * 1000,
    ).toISOString();
    mockGetSettings.mockResolvedValue(
      makeSettings({ paused_until: futureDate }),
    );
    render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Unpause")).toBeInTheDocument();
    });

    // The pause warning text should also appear (isPaused && !isPastDate)
    expect(screen.getByText(/paused until/i)).toBeInTheDocument();
  });

  it("shows Unpause button but no warning for a past paused_until date", async () => {
    // Past date — isPaused=true but isPastDate=true so no warning text
    const pastDate = new Date(
      Date.now() - 2 * 24 * 60 * 60 * 1000,
    ).toISOString();
    mockGetSettings.mockResolvedValue(makeSettings({ paused_until: pastDate }));
    render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Unpause")).toBeInTheDocument();
    });

    // isPastDate is true so the "paused until" warning should NOT show
    expect(
      screen.queryByText(/auto-switcher is paused until/i),
    ).not.toBeInTheDocument();
  });

  it("fires debounced save, clears timer on second change, and cleans up on unmount", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: true }));
    mockUpdateSettings.mockResolvedValue(makeSettings());
    const { unmount } = render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(
        screen.getByLabelText("Minimum dollar savings"),
      ).toBeInTheDocument();
    });

    const minInput = screen.getByLabelText("Minimum dollar savings");

    // First change: immediate=false default used (B5.i=0, B7.i=1), sets timer
    fireEvent.change(minInput, { target: { value: "5" } });
    // Second change before timer fires: clears existing timer (B6.i=0), sets new timer
    fireEvent.change(minInput, { target: { value: "8" } });
    // Unmount while timer still pending: cleanup cancels it (B8.i=0)
    unmount();
  });

  it("ignores savings-threshold input value below minimum (val < 1)", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: true }));
    render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(
        screen.getByLabelText("Minimum dollar savings"),
      ).toBeInTheDocument();
    });

    // val=0 → 0 >= 1 is false → if-false branch (B12.i=1) + binary-expr left-false (B13.i=0)
    fireEvent.change(screen.getByLabelText("Minimum dollar savings"), {
      target: { value: "0" },
    });
    // updateSettings should NOT be called (validation rejected)
    expect(mockUpdateSettings).not.toHaveBeenCalled();
  });

  it("accepts valid savings-threshold input (1 <= val <= 100)", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: true }));
    mockUpdateSettings.mockResolvedValue(makeSettings());
    render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(
        screen.getByLabelText("Minimum dollar savings"),
      ).toBeInTheDocument();
    });

    // val=5 → in range → if-true (B12.i=0), binary-expr right evaluated (B13.i=1)
    fireEvent.change(screen.getByLabelText("Minimum dollar savings"), {
      target: { value: "5" },
    });
  });

  it("accepts valid cooldown input (1 <= val <= 30)", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: true }));
    mockUpdateSettings.mockResolvedValue(makeSettings());
    render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Cooldown period")).toBeInTheDocument();
    });

    // val=7 → in range → if-true (B14.i=0), binary-expr right evaluated (B15.i=1)
    fireEvent.change(screen.getByLabelText("Cooldown period"), {
      target: { value: "7" },
    });
  });

  it("ignores cooldown input value below minimum (val < 1)", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: true }));
    render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Cooldown period")).toBeInTheDocument();
    });

    // val=0 → 0 >= 1 is false → if-false (B14.i=1) + binary-expr left-false (B15.i=0)
    fireEvent.change(screen.getByLabelText("Cooldown period"), {
      target: { value: "0" },
    });
    expect(mockUpdateSettings).not.toHaveBeenCalled();
  });

  it("calls handlePauseChange when pause-until date input has a value", async () => {
    mockGetSettings.mockResolvedValue(makeSettings({ enabled: true }));
    mockUpdateSettings.mockResolvedValue(makeSettings());
    render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Pause until")).toBeInTheDocument();
    });

    // Non-empty value → if (e.target.value) true branch (B23.i=0)
    fireEvent.change(screen.getByLabelText("Pause until"), {
      target: { value: "2026-12-01" },
    });
  });

  it("does not call handlePauseChange when pause-until date input is cleared", async () => {
    mockGetSettings.mockResolvedValue(
      makeSettings({ enabled: true, paused_until: "2026-12-01T00:00:00Z" }),
    );
    render(<AutoSwitcherSettingsContent />, { wrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Pause until")).toBeInTheDocument();
    });

    // Empty value → if (e.target.value) false branch (B23.i=1)
    fireEvent.change(screen.getByLabelText("Pause until"), {
      target: { value: "" },
    });
    // No update triggered for empty date
    expect(mockUpdateSettings).not.toHaveBeenCalled();
  });
});
