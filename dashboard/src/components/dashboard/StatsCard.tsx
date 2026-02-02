"use client";

import type { LucideIcon } from "lucide-react";
import { TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatsCardProps {
  title: string;
  value: number;
  icon: LucideIcon;
  iconColor: string;
  iconBg: string;
  trend?: number;
}

export function StatsCard({
  title,
  value,
  icon: Icon,
  iconColor,
  iconBg,
  trend,
}: StatsCardProps) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-3xl font-bold mt-1">
              {value.toLocaleString()}
            </p>
            {trend !== undefined && trend !== 0 && (
              <div
                className={cn(
                  "flex items-center gap-1 mt-1 text-xs font-medium",
                  trend > 0 ? "text-red-600" : "text-green-600"
                )}
              >
                {trend > 0 ? (
                  <TrendingUp className="h-3 w-3" />
                ) : (
                  <TrendingDown className="h-3 w-3" />
                )}
                <span>
                  {trend > 0 ? "+" : ""}
                  {trend}% from last week
                </span>
              </div>
            )}
          </div>
          <div
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-full",
              iconBg
            )}
          >
            <Icon className={cn("h-6 w-6", iconColor)} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
