'use client';

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  // Navbar is now in root layout, so this just wraps children
  return <>{children}</>;
}
