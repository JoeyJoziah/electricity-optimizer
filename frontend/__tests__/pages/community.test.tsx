import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/lib/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "user-1" } }),
}));

jest.mock("@/lib/store/settings", () => ({
  useSettingsStore: (selector: (s: { utilityTypes: string[] }) => unknown) =>
    selector({ utilityTypes: ["electricity"] }),
}));

jest.mock("@/components/community/CommunityStats", () => ({
  CommunityStats: () => <div data-testid="community-stats" />,
}));

jest.mock("@/components/community/PostForm", () => ({
  PostForm: () => <div data-testid="post-form" />,
}));

jest.mock("@/components/community/PostList", () => ({
  PostList: () => <div data-testid="post-list" />,
}));

jest.mock("@/components/error-boundary", () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

import CommunityPage from "@/app/(app)/community/page";

describe("CommunityPage", () => {
  it("renders the Community heading", () => {
    render(<CommunityPage />);
    expect(
      screen.getByRole("heading", { name: /community/i }),
    ).toBeInTheDocument();
  });

  it("renders CommunityStats", () => {
    render(<CommunityPage />);
    expect(screen.getByTestId("community-stats")).toBeInTheDocument();
  });

  it("renders PostForm", () => {
    render(<CommunityPage />);
    expect(screen.getByTestId("post-form")).toBeInTheDocument();
  });

  it("renders PostList", () => {
    render(<CommunityPage />);
    expect(screen.getByTestId("post-list")).toBeInTheDocument();
  });

  it("does not show utility filter with single utility type", () => {
    render(<CommunityPage />);
    expect(
      screen.queryByTestId("community-utility-filter"),
    ).not.toBeInTheDocument();
  });
});
