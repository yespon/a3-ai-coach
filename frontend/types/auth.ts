export interface UserInfo {
  id: string;
  email: string | null;
  nickname: string | null;
  is_active: boolean;
  is_admin: boolean;
  managed_user_id: string | null;
  employee_no: string | null;
  primary_role: "admin" | "coach" | "student" | null;
  is_coach: boolean;
  created_at: string;
}

export interface CASExchangeResponse {
  ok: boolean;
  user: {
    id: string;
    nickname: string | null;
    email: string | null;
  };
}
