import { render, screen } from "@testing-library/react";
import React from "react";

jest.mock("@/components/agent/AgentChat", () => ({
  AgentChat: () => <div data-testid="agent-chat" />,
}));

jest.mock("@/components/error-boundary", () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

import AssistantPage, { metadata } from "@/app/(app)/assistant/page";

describe("AssistantPage", () => {
  it("renders AgentChat", () => {
    render(<AssistantPage />);
    expect(screen.getByTestId("agent-chat")).toBeInTheDocument();
  });

  it('shows "AI Assistant" heading', () => {
    render(<AssistantPage />);
    expect(
      screen.getByRole("heading", { name: /ai assistant/i }),
    ).toBeInTheDocument();
  });

  it("has correct title metadata", () => {
    expect(metadata.title).toBe("AI Assistant — RateShift");
  });
});
