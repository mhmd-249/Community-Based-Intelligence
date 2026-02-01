// Report types matching backend schema
export type ReportStatus = "open" | "investigating" | "resolved" | "false_alarm";
export type SuspectedDisease = "cholera" | "dengue" | "malaria" | "unknown";
export type UrgencyLevel = "critical" | "high" | "medium" | "low";
export type AlertType = "suspected_outbreak" | "cluster" | "single_case" | "rumor";

export interface Report {
  id: string;
  reporterId: string;
  officerId: string | null;
  conversationId: string;
  status: ReportStatus;
  symptoms: string[];
  suspectedDisease: SuspectedDisease;
  locationText: string;
  locationNormalized: string;
  locationPoint: { lat: number; lng: number } | null;
  onsetText: string;
  onsetDate: string | null;
  casesCount: number;
  deathsCount: number;
  urgency: UrgencyLevel;
  alertType: AlertType;
  dataCompleteness: number;
  rawConversation: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface Officer {
  id: string;
  email: string;
  name: string;
  region: string;
  role: string;
}

export interface Notification {
  id: string;
  reportId: string;
  officerId: string;
  urgency: UrgencyLevel;
  title: string;
  body: string;
  channels: string[];
  sentAt: string;
  readAt: string | null;
}

export interface DashboardStats {
  totalReports: number;
  activeOutbreaks: number;
  criticalAlerts: number;
  resolvedToday: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
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
