"use client";

import { format } from "date-fns";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

interface ConversationViewProps {
  messages: Message[];
}

export function ConversationView({ messages }: ConversationViewProps) {
  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
        No conversation data available
      </div>
    );
  }

  return (
    <div className="max-h-96 space-y-3 overflow-y-auto pr-2">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={cn(
            "flex",
            msg.role === "user" ? "justify-end" : "justify-start"
          )}
        >
          <div
            className={cn(
              "max-w-[80%] rounded-lg px-3 py-2",
              msg.role === "user"
                ? "bg-blue-600 text-white"
                : "bg-muted text-foreground"
            )}
          >
            <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
            {msg.timestamp && (
              <p
                className={cn(
                  "mt-1 text-[10px]",
                  msg.role === "user"
                    ? "text-blue-200"
                    : "text-muted-foreground"
                )}
              >
                {format(new Date(msg.timestamp), "MMM d, h:mm a")}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
