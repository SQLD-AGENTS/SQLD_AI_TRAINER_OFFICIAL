import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useGoogleLogin } from '@react-oauth/google';
import TopBar from '../components/layout/TopBar';
import Alert from '../components/ui/Alert';
import Spinner from '../components/ui/Spinner';
import { authApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, loginAsGuest } = useAuth();
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await authApi.login(email, password);
      login(res.data.access_token, {
        user_id: res.data.user_id,
        username: res.data.username ?? 'User',
        email,
      });
      navigate(from, { replace: true });
    } catch {
      setError('이메일 또는 비밀번호가 올바르지 않습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleGuest = async () => {
    try {
      const res = await authApi.guest();
      loginAsGuest(res.data.access_token, res.data.user_id);
      navigate('/questions');
    } catch {
      navigate('/questions');
    }
  };

  const handleGoogleSuccess = async (accessToken: string) => {
    setError('');
    setLoading(true);
    try {
      const res = await authApi.googleLogin(accessToken);
      login(res.data.access_token, {
        user_id: res.data.user_id,
        username: res.data.username ?? 'User',
        email: '',
      });
      navigate(from, { replace: true });
    } catch {
      setError('구글 로그인에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  const googleLogin = useGoogleLogin({
    onSuccess: (tokenResponse) => handleGoogleSuccess(tokenResponse.access_token),
    onError: () => setError('구글 로그인에 실패했습니다. 다시 시도해 주세요.'),
  });

  return (
    <div className="screen">
      <TopBar />
      <div className="page" style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
        <div className="card" style={{ width: 440, padding: 36 }}>
          <h2 className="t-h2" style={{ textAlign: 'center' }}>로그인</h2>
          <p className="t-body-2" style={{ textAlign: 'center', marginTop: 6 }}>
            SQLD AI에 오신 것을 환영합니다.
          </p>

          {error && <div style={{ marginTop: 20 }}><Alert kind="error" message={error} /></div>}

          <form onSubmit={handleSubmit}>
            <div className="stack" style={{ marginTop: 28, ['--gap' as string]: '16px' }}>
              <div className="field">
                <label className="field-label">이메일</label>
                <input
                  className="input"
                  type="email"
                  placeholder="you@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="field">
                <label className="field-label">비밀번호</label>
                <input
                  className="input"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary btn-lg"
                style={{ width: '100%', marginTop: 36 }}
                disabled={loading}
              >
                {loading ? <Spinner size="sm" /> : '로그인'}
              </button>
            </div>
          </form>

          <div style={{ textAlign: 'center', marginTop: 20 }}>
            <span className="t-caption">계정이 없으신가요? </span>
            <Link to="/register" className="link-pill">회원가입</Link>
          </div>
          <div style={{ textAlign: 'center', marginTop: 10 }}>
            <Link to="/find-account" className="link-pill" style={{ fontSize: 13, color: 'var(--color-text-2)' }}>
              아이디 / 비밀번호 찾기
            </Link>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0' }}>
            <div style={{ flex: 1, height: 1, background: 'var(--border, #e2e8f0)' }} />
            <span className="t-caption" style={{ color: 'var(--color-text-2)', whiteSpace: 'nowrap' }}>또는</span>
            <div style={{ flex: 1, height: 1, background: 'var(--border, #e2e8f0)' }} />
          </div>
          <button
            type="button"
            className="btn btn-outline"
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 12 }}
            onClick={() => googleLogin()}
            disabled={loading}
          >
            <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
              <path fill="#EA4335" d="M24 9.5c3.14 0 5.95 1.08 8.17 2.85l6.1-6.1C34.46 3.01 29.5 1 24 1 14.82 1 7.07 6.48 3.58 14.22l7.1 5.52C12.4 13.35 17.72 9.5 24 9.5z"/>
              <path fill="#4285F4" d="M46.52 24.5c0-1.64-.15-3.22-.42-4.75H24v9h12.67c-.55 2.97-2.2 5.48-4.68 7.18l7.18 5.58C43.27 37.28 46.52 31.37 46.52 24.5z"/>
              <path fill="#FBBC05" d="M10.68 28.26A14.56 14.56 0 0 1 9.5 24c0-1.48.25-2.91.68-4.26l-7.1-5.52A23.94 23.94 0 0 0 0 24c0 3.86.92 7.5 2.54 10.72l8.14-6.46z"/>
              <path fill="#34A853" d="M24 47c5.5 0 10.12-1.82 13.5-4.95l-7.18-5.58c-1.83 1.23-4.17 1.96-6.32 1.96-6.28 0-11.6-3.85-13.32-9.17l-8.14 6.46C7.07 41.52 14.82 47 24 47z"/>
            </svg>
            Google 계정으로 로그인
          </button>
          <button className="btn btn-outline" style={{ width: '100%' }} onClick={handleGuest}>
            게스트로 시작하기
          </button>
        </div>
      </div>
    </div>
  );
}
