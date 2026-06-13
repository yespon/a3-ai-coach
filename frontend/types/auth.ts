export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserInfo {
  id: string;
  email: string | null;
  nickname: string | null;
  is_active: boolean;
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
