import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import TopBar from '../components/layout/TopBar';
import Alert from '../components/ui/Alert';
import Spinner from '../components/ui/Spinner';
import { authApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

export default function RegisterPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [form, setForm] = useState({ username: '', email: '', password: '', confirm: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (form.username.length < 2) return setError('사용자명은 2자 이상이어야 합니다.');
    if (form.password.length < 8) return setError('비밀번호는 8자 이상이어야 합니다.');
    if (form.password !== form.confirm) return setError('비밀번호가 일치하지 않습니다.');

    setError('');
    setLoading(true);
    try {
      const res = await authApi.register(form.username, form.email, form.password);
      login(res.data.access_token, {
        user_id: res.data.user_id,
        username: res.data.username ?? form.username,
        email: form.email,
      });
      navigate('/dashboard');
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? '회원가입에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="screen">
      <TopBar />
      <div className="page" style={{ display: 'flex', justifyContent: 'center', paddingTop: 56 }}>
        <div className="card" style={{ width: 440, padding: 36 }}>
          <h2 className="t-h2" style={{ textAlign: 'center' }}>회원가입</h2>
          <p className="t-body-2" style={{ textAlign: 'center', marginTop: 6 }}>가입 후 자동 로그인됩니다.</p>

          {error && <div style={{ marginTop: 20 }}><Alert kind="error" message={error} /></div>}

          <form onSubmit={handleSubmit}>
            <div className="stack" style={{ marginTop: 28, ['--gap' as string]: '14px' }}>
              <div className="field">
                <label className="field-label">사용자명</label>
                <input className="input" placeholder="2자 이상" value={form.username} onChange={set('username')} required />
              </div>
              <div className="field">
                <label className="field-label">이메일</label>
                <input className="input" type="email" placeholder="you@email.com" value={form.email} onChange={set('email')} required />
              </div>
              <div className="field">
                <label className="field-label">비밀번호</label>
                <input className="input" type="password" placeholder="8자 이상" value={form.password} onChange={set('password')} required />
                <span className="field-hint">영문, 숫자, 특수문자 조합 권장</span>
              </div>
              <div className="field">
                <label className="field-label">비밀번호 확인</label>
                <input className="input" type="password" value={form.confirm} onChange={set('confirm')} required />
              </div>
              <button type="submit" className="btn btn-primary btn-lg" style={{ width: '100%', marginTop: 4 }} disabled={loading}>
                {loading ? <Spinner size="sm" /> : '가입하기'}
              </button>
            </div>
          </form>

          <div style={{ textAlign: 'center', marginTop: 18 }}>
            <span className="t-caption">이미 계정이 있으신가요? </span>
            <Link to="/login" className="link-pill">로그인</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
