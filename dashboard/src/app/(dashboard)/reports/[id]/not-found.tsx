import Link from "next/link";
import { FileX, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ReportNotFound() {
  return (
    <div className="flex min-h-[400px] items-center justify-center p-6">
      <div className="text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-muted">
          <FileX className="h-8 w-8 text-muted-foreground" />
        </div>
        <h1 className="text-2xl font-bold">Report Not Found</h1>
        <p className="mt-2 text-muted-foreground">
          This report doesn&apos;t exist or may have been deleted.
        </p>
        <div className="mt-6">
          <Button asChild variant="outline">
            <Link href="/reports">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Reports
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
