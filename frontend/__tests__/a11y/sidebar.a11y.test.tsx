import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { Sidebar } from "@/components/layout/Sidebar";
import "@testing-library/jest-dom";

let mockPathname = "/dashboard";

jest.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

jest.mock("next/link", () => {
  const MockLink = ({
    children,
    href,
    className,
    onClick,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
    onClick?: () => void;
  }) => (
    <a href={href} className={className} onClick={onClick} {...props}>
      {children}
    </a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

// Mock NotificationBell to avoid QueryClientProvider requirement
jest.mock("@/components/layout/NotificationBell", () => ({
  NotificationBell: () => <div>notifications</div>,
}));

// Mock useAutoSwitcherPendingCount to avoid QueryClientProvider requirement
jest.mock("@/lib/hooks/useAutoSwitcher", () => ({
  useAutoSwitcherPendingCount: () => ({ data: 0, isLoading: false }),
}));

jest.mock("@/lib/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { name: "Test User", email: "test@example.com" },
    isAuthenticated: true,
    isLoading: false,
    signIn: jest.fn(),
    signUp: jest.fn(),
    signOut: jest.fn(),
    signInWithGoogle: jest.fn(),
    signInWithGitHub: jest.fn(),
    sendMagicLink: jest.fn(),
  }),
}));

jest.mock("@/lib/contexts/sidebar-context", () => ({
  useSidebar: () => ({
    isOpen: false,
    toggle: jest.fn(),
    close: jest.fn(),
  }),
}));

jest.mock("@/lib/store/settings", () => ({
  useSettingsStore: () => null,
}));

jest.mock("lucide-react", () => ({
  LayoutDashboard: (props: React.SVGAttributes<SVGElement>) => (
    <svg {...props} />
  ),
  TrendingUp: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Flame: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Sun: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Building2: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Link2: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Calendar: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Bell: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Bot: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Settings: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Fuel: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Droplets: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Waves: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  BarChart3: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  Users: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  LogOut: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  User: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  X: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  HelpCircle: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  FileText: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
  ToggleLeft: (props: React.SVGAttributes<SVGElement>) => <svg {...props} />,
}));

describe("Sidebar a11y", () => {
  beforeEach(() => {
    mockPathname = "/dashboard";
  });

  it("has no accessibility violations when rendered for authenticated user", async () => {
    const { container } = render(<Sidebar />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("has no accessibility violations on non-dashboard page", async () => {
    mockPathname = "/prices";
    const { container } = render(<Sidebar />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("Sidebar a11y (unauthenticated)", () => {
  beforeEach(() => {
    jest.resetModules();
  });

  it("has no accessibility violations when user is not authenticated", async () => {
    jest.mock("@/lib/hooks/useAuth", () => ({
      useAuth: () => ({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        signIn: jest.fn(),
        signUp: jest.fn(),
        signOut: jest.fn(),
        signInWithGoogle: jest.fn(),
        signInWithGitHub: jest.fn(),
        sendMagicLink: jest.fn(),
      }),
    }));

    const { container } = render(<Sidebar />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
