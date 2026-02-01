export default function ReportDetailPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <div>
      <h1 className="text-3xl font-bold mb-6">Report Details</h1>
      <p className="text-muted-foreground">Report ID: {params.id}</p>
      {/* Report detail view will be implemented in Phase 6.3 */}
    </div>
  );
}
