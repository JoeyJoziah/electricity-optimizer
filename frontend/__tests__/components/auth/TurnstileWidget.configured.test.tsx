/**
 * TurnstileWidget with a site key configured. SITE_KEY is read at module
 * load, so this file sets it before requiring the component.
 */
import { render, act } from "@testing-library/react";
import type { ComponentType } from "react";

const SCRIPT_URL =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

type Props = { onTokenChange: (t: string) => void; theme?: "auto" | "dark" };

// The site key is read once at module load, so it is set before the component
// is required (a static import would be hoisted above this line).
process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY = "site-key-123";
const Widget: ComponentType<Props> =
  require("@/components/auth/TurnstileWidget").TurnstileWidget;

describe("TurnstileWidget (site key configured)", () => {
  beforeEach(() => {
    delete window.turnstile;
    document.head
      .querySelectorAll("script")
      .forEach((s) => s.parentNode?.removeChild(s));
  });

  afterAll(() => {
    delete process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
    delete window.turnstile;
  });

  it("renders the challenge and forwards token, error and expiry", () => {
    const renderFn = jest.fn().mockReturnValue("widget-1");
    const remove = jest.fn();
    window.turnstile = { render: renderFn, remove, reset: jest.fn() };
    const onTokenChange = jest.fn();

    const { unmount } = render(
      <Widget onTokenChange={onTokenChange} theme="dark" />,
    );

    expect(renderFn).toHaveBeenCalledTimes(1);
    const opts = renderFn.mock.calls[0][1];
    expect(opts.sitekey).toBe("site-key-123");
    expect(opts.theme).toBe("dark");

    opts.callback("token-abc");
    expect(onTokenChange).toHaveBeenLastCalledWith("token-abc");
    opts["error-callback"]();
    expect(onTokenChange).toHaveBeenLastCalledWith("");
    opts.callback("token-def");
    opts["expired-callback"]();
    expect(onTokenChange).toHaveBeenLastCalledWith("");
    // The dev sentinel is only for the unconfigured case.
    expect(onTokenChange).not.toHaveBeenCalledWith(
      "turnstile-not-configured-dev-only",
    );

    unmount();
    expect(remove).toHaveBeenCalledWith("widget-1");
  });

  it("survives a remove() that throws during cleanup", () => {
    window.turnstile = {
      render: jest.fn().mockReturnValue("widget-2"),
      remove: jest.fn(() => {
        throw new Error("already gone");
      }),
      reset: jest.fn(),
    };

    const { unmount } = render(<Widget onTokenChange={jest.fn()} />);

    expect(() => unmount()).not.toThrow();
  });

  it("injects the script once and renders after it loads", () => {
    const onTokenChange = jest.fn();

    render(<Widget onTokenChange={onTokenChange} />);

    const scripts = document.head.querySelectorAll(
      `script[src="${SCRIPT_URL}"]`,
    );
    expect(scripts).toHaveLength(1);

    const renderFn = jest.fn().mockReturnValue("widget-3");
    window.turnstile = {
      render: renderFn,
      remove: jest.fn(),
      reset: jest.fn(),
    };
    act(() => {
      (scripts[0] as HTMLScriptElement).onload?.(new Event("load"));
    });

    expect(renderFn).toHaveBeenCalledTimes(1);
  });

  it("reuses a script tag another instance already injected", () => {
    const existing = document.createElement("script");
    existing.src = SCRIPT_URL;
    document.head.appendChild(existing);

    render(<Widget onTokenChange={jest.fn()} />);

    expect(
      document.head.querySelectorAll(`script[src="${SCRIPT_URL}"]`),
    ).toHaveLength(1);

    const renderFn = jest.fn().mockReturnValue("widget-4");
    window.turnstile = {
      render: renderFn,
      remove: jest.fn(),
      reset: jest.fn(),
    };
    act(() => {
      existing.dispatchEvent(new Event("load"));
    });

    expect(renderFn).toHaveBeenCalledTimes(1);
  });
});
