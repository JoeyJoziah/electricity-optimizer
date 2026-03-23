import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

jest.mock("@/components/layout/Sidebar", () => ({
  Sidebar: () => <nav data-testid="sidebar">Sidebar</nav>,
}));

jest.mock("@/lib/contexts/sidebar-context", () => ({
  SidebarProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="sidebar-provider">{children}</div>
  ),
}));

jest.mock("@/components/auth/AuthGuard", () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="auth-guard">{children}</div>
  ),
}));

import AppLayout from "@/app/(app)/layout";

describe("AppLayout", () => {
  it("renders the Sidebar", () => {
    render(
      <AppLayout>
        <p>page content</p>
      </AppLayout>,
    );

    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
  });

  it("renders children in a main element", () => {
    render(
      <AppLayout>
        <p data-testid="child">page content</p>
      </AppLayout>,
    );

    const main = screen.getByRole("main");
    expect(main).toBeInTheDocument();
    expect(main).toContainElement(screen.getByTestId("child"));
  });

  it("wraps everything in SidebarProvider", () => {
    render(
      <AppLayout>
        <p>content</p>
      </AppLayout>,
    );

    const provider = screen.getByTestId("sidebar-provider");
    expect(provider).toBeInTheDocument();
    expect(provider).toContainElement(screen.getByTestId("sidebar"));
    expect(provider).toContainElement(screen.getByRole("main"));
  });

  it("applies min-h-screen and flex classes to root div", () => {
    render(
      <AppLayout>
        <p>content</p>
      </AppLayout>,
    );

    const main = screen.getByRole("main");
    const rootDiv = main.parentElement as HTMLElement;
    expect(rootDiv.className).toContain("min-h-screen");
    expect(rootDiv.className).toContain("flex");
  });

  it("applies sidebar offset padding to main element", () => {
    render(
      <AppLayout>
        <p>content</p>
      </AppLayout>,
    );

    const main = screen.getByRole("main");
    // lg:pl-64 provides the sidebar offset
    expect(main.className).toContain("lg:pl-64");
  });

  it("renders a skip-to-content link for keyboard accessibility", () => {
    render(
      <AppLayout>
        <p>content</p>
      </AppLayout>,
    );

    const skipLink = screen.getByRole("link", { name: "Skip to main content" });
    expect(skipLink).toBeInTheDocument();
    expect(skipLink).toHaveAttribute("href", "#main-content");
  });

  it("main element has id for skip-to-content link target", () => {
    render(
      <AppLayout>
        <p>content</p>
      </AppLayout>,
    );

    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main-content");
  });

  it("wraps content in AuthGuard", () => {
    render(
      <AppLayout>
        <p>content</p>
      </AppLayout>,
    );

    const authGuard = screen.getByTestId("auth-guard");
    expect(authGuard).toBeInTheDocument();
    expect(authGuard).toContainElement(screen.getByTestId("sidebar-provider"));
  });
});
