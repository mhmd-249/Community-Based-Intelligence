// Report types
export type ReportStatus = "open" | "investigating" | "resolved" | "false_alarm";
export type UrgencyLevel = "critical" | "high" | "medium" | "low";

export interface Report {
  id: string;
  conversationId: string;
  platform: "telegram" | "whatsapp";
  status: ReportStatus;
  createdAt: string;
  updatedAt: string;

  // MVS Data
  symptoms: string[];
  suspectedDisease: "cholera" | "dengue" | "malaria" | "unknown" | null;
  locationText: string | null;
  locationNormalized: string | null;
  locationCoords: { lat: number; lng: number } | null;
  onsetText: string | null;
  onsetDate: string | null;
  casesCount: number | null;
  deathsCount: number | null;

  // Classification
  dataCompleteness: number;
  urgency: UrgencyLevel;
  alertType: string | null;

  // Investigation
  assignedOfficerId: string | null;
  investigationNotes: string | null;
  outcome: string | null;

  // Conversation
  rawConversation: {
    messages: Array<{
      role: "user" | "assistant";
      content: string;
      timestamp: string;
    }>;
  } | null;
}

export interface Officer {
  id: string;
  email: string;
  fullName: string;
  assignedRegions: string[];
}

export interface ReportListResponse {
  reports: Report[];
  total: number;
  limit: number;
  offset: number;
}

export interface AnalyticsSummary {
  criticalAlerts: number;
  criticalTrend: number;
  activeCases: number;
  casesTrend: number;
  affectedRegions: number;
  reportsToday: number;
  trendData: Array<{
    date: string;
    cholera: number;
    dengue: number;
    malaria: number;
  }>;
  diseaseData: Array<{ name: string; value: number }>;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  urgency: UrgencyLevel;
  reportId?: string;
  timestamp: Date;
  read: boolean;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}
