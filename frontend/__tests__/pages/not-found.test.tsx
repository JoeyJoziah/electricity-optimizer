import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import NotFound from "@/app/not-found";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("NotFound (404 page)", () => {
  beforeEach(() => {
    render(<NotFound />);
  });

  it("renders the 404 status code", () => {
    expect(screen.getByRole("heading", { name: /404/i })).toBeInTheDocument();
  });

  it("renders a page not found message", () => {
    expect(screen.getByText(/page not found/i)).toBeInTheDocument();
  });

  it("renders a link back to the dashboard", () => {
    const link = screen.getByRole("link", { name: /back to dashboard/i });
    expect(link).toHaveAttribute("href", "/dashboard");
  });
});
