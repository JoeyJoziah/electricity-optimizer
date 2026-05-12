import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockMutate = jest.fn();
const mockUseCreatePost = jest.fn();
const mockUseAuth = jest.fn();
const mockUseSettingsStore = jest.fn();

jest.mock("@/lib/hooks/useCommunity", () => ({
  useCreatePost: () => mockUseCreatePost(),
}));

jest.mock("@/lib/hooks/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock("@/lib/store/settings", () => ({
  useSettingsStore: (selector: (s: { region: string }) => unknown) =>
    mockUseSettingsStore(selector),
}));

import { PostForm } from "@/components/community/PostForm";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

function setupAuth(user: { id: string } | null = { id: "user-1" }) {
  mockUseAuth.mockReturnValue({ user });
}

function setupStore() {
  mockUseSettingsStore.mockImplementation(
    (selector: (s: { region: string }) => unknown) =>
      selector({ region: "us_ct" }),
  );
}

function setupMutation(overrides: Record<string, unknown> = {}) {
  mockUseCreatePost.mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    isError: false,
    ...overrides,
  });
}

function setup(authOverride: { id: string } | null = { id: "user-1" }) {
  setupAuth(authOverride);
  setupStore();
  setupMutation();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PostForm", () => {
  beforeEach(() => {
    mockMutate.mockReset();
    mockUseCreatePost.mockReset();
    mockUseAuth.mockReset();
    mockUseSettingsStore.mockReset();
  });

  it("shows auth-required message when user is null", () => {
    setup(null);
    render(<PostForm />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("post-form-auth-required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toBeInTheDocument();
  });

  it("shows collapsed expand button when user is authenticated", () => {
    setup();
    render(<PostForm />, { wrapper: makeWrapper() });
    expect(screen.getByTestId("post-form-expand")).toBeInTheDocument();
  });

  it("expands form when expand button is clicked", () => {
    setup();
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    expect(screen.getByTestId("post-form")).toBeInTheDocument();
  });

  it("renders Post Type and Utility Type selects after expand", () => {
    setup();
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    expect(screen.getByTestId("post-type-select")).toBeInTheDocument();
    expect(screen.getByTestId("utility-type-select")).toBeInTheDocument();
  });

  it("uses defaultUtilityType as initial utility selection", () => {
    setup();
    render(<PostForm defaultUtilityType="natural_gas" />, {
      wrapper: makeWrapper(),
    });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    expect(screen.getByTestId("utility-type-select")).toHaveValue(
      "natural_gas",
    );
  });

  it("shows title and body validation errors on empty submit", async () => {
    setup();
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    fireEvent.click(screen.getByTestId("post-submit-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("title-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("body-error")).toBeInTheDocument();
  });

  it("shows rate fields only when post type is rate_report", () => {
    setup();
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    expect(screen.queryByTestId("rate-fields")).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId("post-type-select"), {
      target: { value: "rate_report" },
    });
    expect(screen.getByTestId("rate-fields")).toBeInTheDocument();
  });

  it("calls mutate with form data on valid submit", () => {
    setup();
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));

    fireEvent.change(screen.getByTestId("post-title-input"), {
      target: { value: "Great tip for off-peak" },
    });
    fireEvent.change(screen.getByTestId("post-body-input"), {
      target: { value: "Here is a detailed explanation of off-peak savings" },
    });
    fireEvent.click(screen.getByTestId("post-submit-btn"));

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Great tip for off-peak",
        body: "Here is a detailed explanation of off-peak savings",
        post_type: "tip",
        utility_type: "electricity",
        region: "us_ct",
      }),
      expect.any(Object),
    );
  });

  it("collapses form and calls onSuccess after successful mutation", async () => {
    const onSuccess = jest.fn();
    mockUseCreatePost.mockReturnValue({
      isPending: false,
      isError: false,
      mutate: jest.fn().mockImplementation((_vars, opts) => {
        opts.onSuccess();
      }),
    });
    setupAuth();
    setupStore();

    render(<PostForm onSuccess={onSuccess} />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    fireEvent.change(screen.getByTestId("post-title-input"), {
      target: { value: "Great tip for saving money" },
    });
    fireEvent.change(screen.getByTestId("post-body-input"), {
      target: { value: "Here is a detailed explanation of this great tip" },
    });
    fireEvent.click(screen.getByTestId("post-submit-btn"));

    await waitFor(() =>
      expect(screen.queryByTestId("post-form")).not.toBeInTheDocument(),
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("disables submit button when isPending=true", () => {
    setup();
    setupMutation({ isPending: true });
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    expect(screen.getByTestId("post-submit-btn")).toBeDisabled();
    expect(screen.getByTestId("post-submit-btn")).toHaveTextContent(
      "Posting...",
    );
  });

  it("shows error message when isError=true", () => {
    setup();
    setupMutation({ isError: true });
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    expect(screen.getByTestId("post-submit-error")).toBeInTheDocument();
  });

  it("Cancel button collapses the form", () => {
    setup();
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByTestId("post-form")).not.toBeInTheDocument();
    expect(screen.getByTestId("post-form-expand")).toBeInTheDocument();
  });

  it("renders consent text", () => {
    setup();
    render(<PostForm />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByTestId("post-form-expand"));
    expect(screen.getByTestId("consent-text")).toBeInTheDocument();
  });
});
