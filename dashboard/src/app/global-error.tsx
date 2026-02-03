"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    console.error("Global error:", error);
  }, [error]);

  return (
    <html lang="en">
      <body className="bg-slate-50">
        <div className="flex min-h-screen items-center justify-center p-6">
          <div className="w-full max-w-md rounded-lg border bg-white p-8 shadow-lg">
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-red-100">
                <AlertTriangle className="h-7 w-7 text-red-600" />
              </div>
              <h1 className="text-2xl font-bold text-slate-900">
                Application Error
              </h1>
              <p className="mt-2 text-slate-600">
                A critical error has occurred. Please try refreshing the page.
              </p>
              {error.digest && (
                <p className="mt-2 text-xs text-slate-400">
                  Error ID: {error.digest}
                </p>
              )}
            </div>
            <div className="mt-6 flex justify-center gap-4">
              <button
                onClick={() => window.location.reload()}
                className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Refresh Page
              </button>
              <button
                onClick={reset}
                className="inline-flex items-center rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                Try Again
              </button>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
