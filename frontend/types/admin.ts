import type { ChatHistoryItem } from "./chat";

export type ManagedUserRole = "admin" | "coach" | "student";

export interface ManagedUser {
  id: string;
  employee_no: string;
  name: string | null;
  email: string | null;
  department_level1: string | null;
  primary_role: ManagedUserRole;
  is_coach: boolean;
  coach_id: string | null;
  coach_name: string | null;
  enabled: boolean;
  source: string;
  is_system_admin: boolean;
  created_at: string;
  updated_at: string;
}

export interface ManagedUserPayload {
  employee_no: string;
  name?: string | null;
  email?: string | null;
  department_level1?: string | null;
  primary_role: ManagedUserRole;
  is_coach: boolean;
  coach_id?: string | null;
  enabled: boolean;
}

export interface CoachOption {
  id: string;
  employee_no: string;
  name: string | null;
  department_level1: string | null;
}

export interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: { row: number; reason: string }[];
}

export interface ConversationUserSummary {
  managed_user_id: string;
  employee_no: string;
  name: string | null;
  department_level1: string | null;
  coach_id: string | null;
  coach_name: string | null;
  session_count: number;
  latest_session_at: string | null;
}

export interface AdminSessionSummary {
  session_id: string;
  created_at: string;
  updated_at: string;
  latest_preview: string;
  message_count: number;
}

export interface AdminConversationDetail {
  session_id: string;
  student: {
    managed_user_id: string;
    employee_no: string;
    name: string | null;
    department_level1: string | null;
  };
  created_at: string;
  updated_at: string;
  history: ChatHistoryItem[];
}

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export type ManagedUserCoachFilter = "all" | "unassigned" | string; // "all" | "unassigned" | "<uuid>"

export type ManagedUserHasEmail = boolean | null;

export interface ManagedUserFilters {
  q?: string | null;
  role?: "admin" | "coach" | "student" | null;
  enabled?: boolean | null;
  coach_filter?: ManagedUserCoachFilter;
  department_level1?: string | null;
  has_email?: ManagedUserHasEmail;
}
