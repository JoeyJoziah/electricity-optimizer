/**
 * Auth Layout
 *
 * Standalone layout for authentication pages (login, signup, callback, etc.).
 * Does NOT include the Sidebar or other app chrome so auth pages render
 * full-screen without navigation clutter.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
