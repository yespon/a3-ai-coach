export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserInfo {
  id: string;
  email: string;
  nickname: string | null;
  is_active: boolean;
  created_at: string;
}
