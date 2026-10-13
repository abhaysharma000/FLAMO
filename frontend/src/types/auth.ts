export interface AuthStatusResponse {
  auth_enabled: boolean;
  authenticated: boolean;
  username?: string | null;
  csrf_token?: string | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  success: boolean;
  authenticated?: boolean;
  username: string;
  csrf_token: string;
  expires_at: number;
}
