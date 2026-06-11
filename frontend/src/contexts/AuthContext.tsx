import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface User {
  user_id: string;
  username: string;
  email: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isGuest: boolean;
}

interface AuthContextValue extends AuthState {
  login: (token: string, user: User) => void;
  loginAsGuest: (token: string, user_id: string) => void;
  logout: () => void;
  updateUsername: (newUsername: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'sqld_token';
const USER_KEY = 'sqld_user';
const GUEST_KEY = 'sqld_is_guest';

function loadInitialState(): AuthState {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const user = localStorage.getItem(USER_KEY);
    const isGuest = localStorage.getItem(GUEST_KEY) === 'true';
    return {
      token,
      user: user ? JSON.parse(user) : null,
      isGuest,
    };
  } catch {
    return { token: null, user: null, isGuest: false };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadInitialState);

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
    setState({ token: null, user: null, isGuest: false });
  }, []);

  const updateUsername = useCallback((newUsername: string) => {
    setState((prev) => {
      if (!prev.user) return prev;
      const updated = { ...prev.user, username: newUsername };
      localStorage.setItem(USER_KEY, JSON.stringify(updated));
      return { ...prev, user: updated };
    });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, loginAsGuest, logout, updateUsername }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
