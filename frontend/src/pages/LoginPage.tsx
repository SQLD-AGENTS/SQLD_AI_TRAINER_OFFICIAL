import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
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
          <div className="divider" style={{ margin: '20px 0' }} />
          <button className="btn btn-outline" style={{ width: '100%' }} onClick={handleGuest}>
            게스트로 시작하기
          </button>
        </div>
      </div>
    </div>
  );
}
