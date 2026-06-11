import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';

interface User {
  user_id: string;
  username: string;
  email: string;
  avatar_url?: string | null;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isGuest: boolean;
  showSolvedStatus: boolean;
}

interface AuthContextValue extends AuthState {
  login: (token: string, user: User) => void;
  loginAsGuest: (token: string, user_id: string) => void;
  logout: () => void;
  updateUsername: (newUsername: string) => void;
  updateAvatarUrl: (url: string | null) => void;
  toggleShowSolvedStatus: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'sqld_token';
const USER_KEY = 'sqld_user';
const GUEST_KEY = 'sqld_is_guest';
const SOLVED_TOGGLE_KEY = 'sqld_show_solved';

function loadInitialState(): AuthState {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const user = localStorage.getItem(USER_KEY);
    const isGuest = localStorage.getItem(GUEST_KEY) === 'true';
    const showSolvedStatus = localStorage.getItem(SOLVED_TOGGLE_KEY) !== 'false';
    return {
      token,
      user: user ? JSON.parse(user) : null,
      isGuest,
      showSolvedStatus,
    };
  } catch {
    return { token: null, user: null, isGuest: false, showSolvedStatus: true };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadInitialState);
  const queryClient = useQueryClient();

  const login = useCallback((token: string, user: User) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    localStorage.removeItem(GUEST_KEY);
    setState({ token, user, isGuest: false });
  }, []);

  const loginAsGuest = useCallback((token: string, user_id: string) => {
    const guestUser: User = { user_id, username: '게스트', email: '' };
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(guestUser));
    localStorage.setItem(GUEST_KEY, 'true');
    setState({ token, user: guestUser, isGuest: true });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(GUEST_KEY);
    setState((prev) => ({ token: null, user: null, isGuest: false, showSolvedStatus: prev.showSolvedStatus }));
    queryClient.clear();
  }, [queryClient]);

  const updateUsername = useCallback((newUsername: string) => {
    setState((prev) => {
      if (!prev.user) return prev;
      const updated = { ...prev.user, username: newUsername };
      localStorage.setItem(USER_KEY, JSON.stringify(updated));
      return { ...prev, user: updated };
    });
  }, []);

  const updateAvatarUrl = useCallback((url: string | null) => {
    setState((prev) => {
      if (!prev.user) return prev;
      const updated = { ...prev.user, avatar_url: url };
      localStorage.setItem(USER_KEY, JSON.stringify(updated));
      return { ...prev, user: updated };
    });
  }, []);

  const toggleShowSolvedStatus = useCallback(() => {
    setState((prev) => {
      const next = !prev.showSolvedStatus;
      localStorage.setItem(SOLVED_TOGGLE_KEY, String(next));
      return { ...prev, showSolvedStatus: next };
    });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, loginAsGuest, logout, updateUsername, updateAvatarUrl, toggleShowSolvedStatus }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
