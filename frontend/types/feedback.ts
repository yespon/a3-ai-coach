import type { Paginated } from "./admin";

export type FeedbackStatus = "open" | "read" | "resolved";

export interface FeedbackAttachment {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  url: string;
}

export interface FeedbackSubmitter {
  employee_no: string | null;
  name: string | null;
  email: string | null;
  department_level1?: string | null;
  primary_role?: "admin" | "coach" | "student" | null;
}

export interface FeedbackListItem {
  id: string;
  submitter: FeedbackSubmitter;
  content_excerpt: string;
  attachment_count: number;
  status: FeedbackStatus;
  created_at: string;
}

export interface FeedbackDetail {
  id: string;
  submitter: FeedbackSubmitter;
  content: string;
  status: FeedbackStatus;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  read_at: string | null;
  resolved_at: string | null;
  attachments: FeedbackAttachment[];
}

export interface FeedbackFilters {
  status?: "all" | FeedbackStatus;
  q?: string | null;
}

export type PaginatedFeedbackList = Paginated<FeedbackListItem>;
