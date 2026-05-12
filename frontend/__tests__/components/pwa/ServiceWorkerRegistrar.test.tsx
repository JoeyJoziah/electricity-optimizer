import { render } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

import { ServiceWorkerRegistrar } from "@/components/pwa/ServiceWorkerRegistrar";

describe("ServiceWorkerRegistrar", () => {
  const originalRegister = navigator.serviceWorker?.register;

  beforeEach(() => {
    Object.defineProperty(navigator, "serviceWorker", {
      value: { register: jest.fn().mockResolvedValue({ scope: "/app/" }) },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    if (originalRegister !== undefined) {
      Object.defineProperty(navigator, "serviceWorker", {
        value: { register: originalRegister },
        writable: true,
        configurable: true,
      });
    }
  });

  it("renders nothing (returns null)", () => {
    const { container } = render(<ServiceWorkerRegistrar />);
    expect(container.firstChild).toBeNull();
  });

  it("calls navigator.serviceWorker.register with /sw.js", () => {
    render(<ServiceWorkerRegistrar />);
    expect(navigator.serviceWorker.register).toHaveBeenCalledWith("/sw.js");
  });

  it("registers and logs on success", async () => {
    const consoleSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    render(<ServiceWorkerRegistrar />);
    // Allow the microtask/promise to resolve
    await Promise.resolve();
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining("[SW] Registered:"),
      expect.any(String),
    );
    consoleSpy.mockRestore();
  });
});
