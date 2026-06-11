import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('sqld_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Auth ──────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post('/auth/login', { email, password }),
  register: (username: string, email: string, password: string) =>
    apiClient.post('/auth/register', { username, email, password }),
  guest: () => apiClient.post('/auth/guest'),
  googleLogin: (accessToken: string) =>
    apiClient.post<{ access_token: string; user_id: string; username: string; is_new_user: boolean; avatar_url?: string | null }>('/auth/google', { access_token: accessToken }),
  checkUsername: (username: string) =>
    apiClient.get<{ available: boolean }>('/auth/check-username', { params: { username } }),
  findUsername: (email: string) =>
    apiClient.post<{ username: string }>('/auth/find-username', { email }),
  resetPassword: (email: string) =>
    apiClient.post<{ temp_password: string }>('/auth/reset-password', { email }),
};

// ── Questions ─────────────────────────────────────────
export interface QuestionFilters {
  chapter_name?: string;
  difficulty?: string;
  question_type?: string;
  limit?: number;
  offset?: number;
}

export const questionsApi = {
  list: (filters: QuestionFilters) =>
    apiClient.get('/questions', { params: filters }),
  detail: (id: string) =>
    apiClient.get(`/questions/${id}`),
};

// ── Logs ──────────────────────────────────────────────
export interface SolvedSummary {
  solved_ids: string[];
  correct_ids: string[];
}

export interface CheckSolvedResult {
  is_solved: boolean;
  is_correct: boolean | null;
}

export const logsApi = {
  submit: (question_id: string, selected: number) =>
    apiClient.post('/logs', { question_id, selected_answer: selected }),
  getSolvedSummary: () =>
    apiClient.get<SolvedSummary>('/logs/solved'),
  checkSolved: (question_id: string) =>
    apiClient.get<CheckSolvedResult>(`/logs/check/${question_id}`),
};

// ── Predict ───────────────────────────────────────────
export const predictApi = {
  errorProb: (user_id: string, question_id: string) =>
    apiClient.post('/predict', { user_id, question_id }),
};

// ── Explain ───────────────────────────────────────────
export const explainApi = {
  explain: (question_id: string) =>
    apiClient.post('/explain', { question_id }),
};

// ── Progress ──────────────────────────────────────────
export const progressApi = {
  get: (user_id: string) =>
    apiClient.get(`/progress/${user_id}`),
};

// ── Recommend ─────────────────────────────────────────
export const recommendApi = {
  get: (user_id: string, top_n = 10, use_zpd = true) =>
    apiClient.post(`/recommend/${user_id}`, { top_n, use_zpd }),
};

// ── Profile ───────────────────────────────────────────
export interface UserProfile {
  user_id: string;
  email: string;
  username: string;
  avatar_url?: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_active: boolean;
  social_provider?: string | null;
}

export interface UserUpdatePayload {
  username?: string;
  email?: string;
  password?: string;
  current_password?: string;
}

export const profileApi = {
  getMe: () =>
    apiClient.get<UserProfile>('/auth/users/me'),
  updateMe: (payload: UserUpdatePayload) =>
    apiClient.put<UserProfile>('/auth/users/me', payload),
  deleteMe: (password: string) =>
    apiClient.delete('/auth/users/me', { data: { password } }),
  checkEmail: (email: string) =>
    apiClient.get<{ available: boolean }>('/auth/check-email', { params: { email } }),
  uploadAvatar: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post<UserProfile>('/auth/users/me/avatar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  deleteAvatar: () =>
    apiClient.delete<UserProfile>('/auth/users/me/avatar'),
  revokeAllSessions: () =>
    apiClient.post<{ access_token: string; user_id: string; username: string }>('/auth/users/me/revoke-all'),
};

export { BASE_URL };
