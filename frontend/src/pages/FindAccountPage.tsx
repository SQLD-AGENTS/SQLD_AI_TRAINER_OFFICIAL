import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import TopBar from '../components/layout/TopBar';
import Spinner from '../components/ui/Spinner';
import { authApi } from '../services/api';

type Tab = 'username' | 'password';

export default function FindAccountPage() {
  const [tab, setTab] = useState<Tab>('username');

  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState('');

  const reset = () => {
    setEmail('');
    setError('');
    setResult('');
  };

  const switchTab = (t: Tab) => {
    setTab(t);
    reset();
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setResult('');
    setLoading(true);
    try {
      if (tab === 'username') {
        const res = await authApi.findUsername(email);
        setResult(res.data.username);
      } else {
        const res = await authApi.resetPassword(email);
        setResult(res.data.temp_password);
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? '처리 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="screen">
      <TopBar />
      <div className="page" style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
        <div className="card" style={{ width: 440, padding: 36 }}>
          <h2 className="t-h2" style={{ textAlign: 'center' }}>계정 찾기</h2>

          <div style={{ display: 'flex', gap: 0, marginTop: 24, borderBottom: '1px solid var(--color-border)' }}>
            {(['username', 'password'] as Tab[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => switchTab(t)}
                style={{
                  flex: 1,
                  padding: '10px 0',
                  background: 'none',
                  border: 'none',
                  borderBottom: tab === t ? '2px solid var(--color-primary)' : '2px solid transparent',
                  color: tab === t ? 'var(--color-primary)' : 'var(--color-text-2)',
                  fontWeight: tab === t ? 600 : 400,
                  cursor: 'pointer',
                  fontSize: 14,
                  marginBottom: -1,
                }}
              >
                {t === 'username' ? '아이디 찾기' : '비밀번호 찾기'}
              </button>
            ))}
          </div>

          {!result ? (
            <form onSubmit={handleSubmit}>
              <div className="stack" style={{ marginTop: 28, ['--gap' as string]: '14px' }}>
                <p className="t-body-2" style={{ color: 'var(--color-text-2)' }}>
                  {tab === 'username'
                    ? '가입 시 사용한 이메일을 입력하면 사용자명을 확인할 수 있습니다.'
                    : '가입 시 사용한 이메일을 입력하면 임시 비밀번호를 발급해 드립니다.'}
                </p>
                <div className="field">
                  <label className="field-label">이메일</label>
                  <input
                    className="input"
                    type="email"
                    placeholder="you@email.com"
                    value={email}
                    onChange={(e) => { setEmail(e.target.value); setError(''); }}
                    required
                  />
                  {error && <span className="field-error">{error}</span>}
                </div>
                <button
                  type="submit"
                  className="btn btn-primary btn-lg"
                  style={{ width: '100%', marginTop: 4 }}
                  disabled={loading}
                >
                  {loading ? <Spinner size="sm" /> : (tab === 'username' ? '아이디 확인' : '임시 비밀번호 발급')}
                </button>
              </div>
            </form>
          ) : (
            <div className="stack" style={{ marginTop: 28, ['--gap' as string]: '16px', textAlign: 'center' }}>
              {tab === 'username' ? (
                <>
                  <p className="t-body-2" style={{ color: 'var(--color-text-2)' }}>
                    해당 이메일로 가입된 사용자명입니다.
                  </p>
                  <div style={{
                    padding: '16px 20px',
                    background: 'var(--color-bg-2)',
                    borderRadius: 10,
                    fontSize: 20,
                    fontWeight: 700,
                    color: 'var(--color-text)',
                  }}>
                    {result}
                  </div>
                </>
              ) : (
                <>
                  <p className="t-body-2" style={{ color: 'var(--color-text-2)' }}>
                    임시 비밀번호가 발급되었습니다.<br />
                    로그인 후 반드시 비밀번호를 변경해주세요.
                  </p>
                  <div style={{
                    padding: '16px 20px',
                    background: 'var(--color-bg-2)',
                    borderRadius: 10,
                    fontSize: 18,
                    fontWeight: 700,
                    letterSpacing: 2,
                    color: 'var(--color-text)',
                    fontFamily: 'monospace',
                  }}>
                    {result}
                  </div>
                </>
              )}
              <button
                type="button"
                className="btn btn-outline"
                style={{ width: '100%' }}
                onClick={reset}
              >
                다시 찾기
              </button>
            </div>
          )}

          <div style={{ textAlign: 'center', marginTop: 20 }}>
            <Link to="/login" className="link-pill">로그인으로 돌아가기</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
