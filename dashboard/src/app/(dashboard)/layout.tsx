export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar will be implemented in Phase 6.2 */}
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
