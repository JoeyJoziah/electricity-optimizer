import React from "react";
import { render, screen, act } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ToastProvider, useToast } from "@/lib/contexts/toast-context";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <ToastProvider>{children}</ToastProvider>;
  };
}

// ---------------------------------------------------------------------------
// useToast — guard
// ---------------------------------------------------------------------------
describe("useToast", () => {
  it("throws when used outside ToastProvider", () => {
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});

    expect(() => {
      renderHook(() => useToast());
    }).toThrow("useToast must be used within ToastProvider");

    spy.mockRestore();
  });

  it("does not throw when used inside ToastProvider", () => {
    const wrapper = createWrapper();
    expect(() => {
      renderHook(() => useToast(), { wrapper });
    }).not.toThrow();
  });

  it("provides all expected methods", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    expect(typeof result.current.toast).toBe("function");
    expect(typeof result.current.success).toBe("function");
    expect(typeof result.current.error).toBe("function");
    expect(typeof result.current.warning).toBe("function");
    expect(typeof result.current.info).toBe("function");
  });
});

// ---------------------------------------------------------------------------
// ToastProvider — children rendering
// ---------------------------------------------------------------------------
describe("ToastProvider", () => {
  it("renders its children", () => {
    render(
      <ToastProvider>
        <div data-testid="child">Hello</div>
      </ToastProvider>,
    );
    expect(screen.getByTestId("child")).toBeInTheDocument();
  });

  it("renders an aria-live polite region for screen readers", () => {
    render(<ToastProvider>{null}</ToastProvider>);
    const liveRegion = document.querySelector('[aria-live="polite"]');
    expect(liveRegion).not.toBeNull();
  });

  it("initially renders no toast alerts", () => {
    render(<ToastProvider>{null}</ToastProvider>);
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// toast() — base method
// ---------------------------------------------------------------------------
describe("toast() method", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      jest.runOnlyPendingTimers();
    });
    jest.useRealTimers();
  });

  it("adds a toast with correct variant and title", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({ variant: "success", title: "Saved!" });
    });

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Saved!")).toBeInTheDocument();
  });

  it("adds a toast with optional description", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({
        variant: "info",
        title: "Update available",
        description: "A new version has been released.",
      });
    });

    expect(screen.getByText("Update available")).toBeInTheDocument();
    expect(
      screen.getByText("A new version has been released."),
    ).toBeInTheDocument();
  });

  it("auto-dismisses after the default 5000ms duration", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({ variant: "success", title: "Auto-dismiss me" });
    });

    expect(screen.getByRole("alert")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(5000);
    });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("respects a custom duration", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({
        variant: "info",
        title: "Short toast",
        duration: 1000,
      });
    });

    expect(screen.getByText("Short toast")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(999);
    });
    expect(screen.getByText("Short toast")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(1);
    });
    expect(screen.queryByText("Short toast")).not.toBeInTheDocument();
  });

  it("does not auto-dismiss when duration is 0", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({
        variant: "warning",
        title: "Sticky toast",
        duration: 0,
      });
    });

    act(() => {
      jest.advanceTimersByTime(60000);
    });

    expect(screen.getByText("Sticky toast")).toBeInTheDocument();
  });

  it("stacks multiple toasts", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({ variant: "success", title: "Toast one" });
      result.current.toast({ variant: "error", title: "Toast two" });
      result.current.toast({ variant: "info", title: "Toast three" });
    });

    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(3);
  });

  it("removes only the timed-out toast from a stack", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({
        variant: "success",
        title: "Keep me",
        duration: 0,
      });
      result.current.toast({
        variant: "error",
        title: "Remove me",
        duration: 1000,
      });
    });

    expect(screen.getAllByRole("alert")).toHaveLength(2);

    act(() => {
      jest.advanceTimersByTime(1000);
    });

    const remaining = screen.getAllByRole("alert");
    expect(remaining).toHaveLength(1);
    expect(screen.getByText("Keep me")).toBeInTheDocument();
  });

  it("each toast gets a unique id", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({ variant: "success", title: "First", duration: 0 });
      result.current.toast({
        variant: "success",
        title: "Second",
        duration: 0,
      });
    });

    // Both should be visible with distinct keys (unique ids)
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Convenience methods: success / error / warning / info
// ---------------------------------------------------------------------------
describe("convenience toast methods", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      jest.runOnlyPendingTimers();
    });
    jest.useRealTimers();
  });

  it("success() creates a success-variant toast", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.success("Profile saved");
    });

    expect(screen.getByText("Profile saved")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("success() accepts an optional description", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.success("Done", "Your settings have been applied.");
    });

    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(
      screen.getByText("Your settings have been applied."),
    ).toBeInTheDocument();
  });

  it("error() creates an error-variant toast", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.error("Something went wrong");
    });

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("error() accepts an optional description", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.error("Request failed", "Please try again later.");
    });

    expect(screen.getByText("Request failed")).toBeInTheDocument();
    expect(screen.getByText("Please try again later.")).toBeInTheDocument();
  });

  it("warning() creates a warning-variant toast", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.warning("Low balance");
    });

    expect(screen.getByText("Low balance")).toBeInTheDocument();
  });

  it("warning() accepts an optional description", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.warning("Heads up", "Your trial expires soon.");
    });

    expect(screen.getByText("Heads up")).toBeInTheDocument();
    expect(screen.getByText("Your trial expires soon.")).toBeInTheDocument();
  });

  it("info() creates an info-variant toast", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.info("New feature available");
    });

    expect(screen.getByText("New feature available")).toBeInTheDocument();
  });

  it("info() accepts an optional description", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.info("Update", "Check out the new dashboard.");
    });

    expect(screen.getByText("Update")).toBeInTheDocument();
    expect(
      screen.getByText("Check out the new dashboard."),
    ).toBeInTheDocument();
  });

  it("all four convenience methods produce alert elements", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.success("Success toast", undefined);
      result.current.error("Error toast", undefined);
      result.current.warning("Warning toast", undefined);
      result.current.info("Info toast", undefined);
    });

    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(4);
  });
});

// ---------------------------------------------------------------------------
// Manual dismiss via Dismiss button
// ---------------------------------------------------------------------------
describe("manual toast dismissal", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      jest.runOnlyPendingTimers();
    });
    jest.useRealTimers();
  });

  it("removes the toast when the dismiss button is clicked", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({
        variant: "info",
        title: "Click to dismiss",
        duration: 0,
      });
    });

    expect(screen.getByText("Click to dismiss")).toBeInTheDocument();

    act(() => {
      screen.getByRole("button", { name: /dismiss/i }).click();
    });

    expect(screen.queryByText("Click to dismiss")).not.toBeInTheDocument();
  });

  it("clears the auto-dismiss timer when toast is manually dismissed", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({
        variant: "success",
        title: "Dismiss early",
        duration: 5000,
      });
    });

    // Dismiss before the 5s timer fires
    act(() => {
      screen.getByRole("button", { name: /dismiss/i }).click();
    });

    expect(screen.queryByText("Dismiss early")).not.toBeInTheDocument();

    // Advance past the original timeout — no error should occur
    act(() => {
      jest.advanceTimersByTime(5000);
    });

    expect(screen.queryByText("Dismiss early")).not.toBeInTheDocument();
  });

  it("dismisses the correct toast from a stack", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useToast(), { wrapper });

    act(() => {
      result.current.toast({ variant: "success", title: "Stay", duration: 0 });
      result.current.toast({ variant: "error", title: "Go away", duration: 0 });
    });

    const dismissButtons = screen.getAllByRole("button", { name: /dismiss/i });
    // 'Go away' is the second toast; click its dismiss button
    act(() => {
      dismissButtons[1]!.click();
    });

    expect(screen.queryByText("Go away")).not.toBeInTheDocument();
    expect(screen.getByText("Stay")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Timer cleanup on unmount
// ---------------------------------------------------------------------------
describe("ToastProvider cleanup on unmount", () => {
  it("clears pending timers when the provider unmounts", () => {
    jest.useFakeTimers();
    const clearTimeoutSpy = jest.spyOn(global, "clearTimeout");

    const { result, unmount } = renderHook(() => useToast(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.toast({
        variant: "info",
        title: "Pending",
        duration: 5000,
      });
    });

    unmount();

    // clearTimeout should have been called during cleanup
    expect(clearTimeoutSpy).toHaveBeenCalled();

    clearTimeoutSpy.mockRestore();
    act(() => {
      jest.runOnlyPendingTimers();
    });
    jest.useRealTimers();
  });
});
