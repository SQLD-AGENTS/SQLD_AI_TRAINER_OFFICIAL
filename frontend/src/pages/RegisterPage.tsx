import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useGoogleLogin } from '@react-oauth/google';
import TopBar from '../components/layout/TopBar';
import Spinner from '../components/ui/Spinner';
import { authApi, profileApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

interface FieldErrors {
  username?: string;
  email?: string;
  password?: string;
  confirm?: string;
  form?: string;
}

export default function RegisterPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [form, setForm] = useState({ username: '', email: '', password: '', confirm: '' });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [loading, setLoading] = useState(false);
  const [googleError, setGoogleError] = useState('');

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    setErrors((prev) => ({ ...prev, [k]: undefined, form: undefined }));
  };

  const setFieldError = (field: keyof FieldErrors, msg: string) =>
    setErrors((prev) => ({ ...prev, [field]: msg }));

  const handleUsernameBlur = async () => {
    if (form.username.length < 2) return;
    try {
      const res = await authApi.checkUsername(form.username);
      if (!res.data.available) setFieldError('username', '이미 사용 중인 사용자명입니다.');
    } catch {
      // 네트워크 오류는 조용히 무시 (제출 시 서버에서 최종 검증)
    }
  };

  const handleEmailBlur = async () => {
    if (!form.email.includes('@')) return;
    try {
      const res = await profileApi.checkEmail(form.email);
      if (!res.data.available) setFieldError('email', '이미 사용 중인 이메일입니다.');
    } catch {
      // 네트워크 오류는 조용히 무시
    }
  };

  const validate = (): boolean => {
    const next: FieldErrors = {};
    if (form.username.length < 2) next.username = '사용자명은 2자 이상이어야 합니다.';
    if (!form.email.includes('@')) next.email = '올바른 이메일 주소를 입력해주세요.';
    if (form.password.length < 8) next.password = '비밀번호는 8자 이상이어야 합니다.';
    if (form.password !== form.confirm) next.confirm = '비밀번호가 일치하지 않습니다.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

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
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '';
      if (detail.includes('사용자명')) {
        setFieldError('username', detail);
      } else if (detail.includes('이메일')) {
        setFieldError('email', detail);
      } else {
        setErrors((prev) => ({ ...prev, form: detail || '회원가입에 실패했습니다.' }));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSuccess = async (accessToken: string) => {
    setGoogleError('');
    setLoading(true);
    try {
      const res = await authApi.googleLogin(accessToken);
      login(res.data.access_token, {
        user_id: res.data.user_id,
        username: res.data.username ?? 'User',
        email: '',
      });
      navigate('/dashboard');
    } catch {
      setGoogleError('구글 로그인에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  const googleLogin = useGoogleLogin({
    onSuccess: (tokenResponse) => handleGoogleSuccess(tokenResponse.access_token),
    onError: () => setGoogleError('구글 로그인에 실패했습니다. 다시 시도해 주세요.'),
  });

  return (
    <div className="screen">
      <TopBar />
      <div className="page" style={{ display: 'flex', justifyContent: 'center', paddingTop: 56 }}>
        <div className="card" style={{ width: 440, padding: 36 }}>
          <h2 className="t-h2" style={{ textAlign: 'center' }}>회원가입</h2>
          <p className="t-body-2" style={{ textAlign: 'center', marginTop: 6 }}>가입 후 자동 로그인됩니다.</p>

          <button
            type="button"
            className="btn btn-outline"
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 4 }}
            onClick={() => googleLogin()}
            disabled={loading}
          >
            <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
              <path fill="#EA4335" d="M24 9.5c3.14 0 5.95 1.08 8.17 2.85l6.1-6.1C34.46 3.01 29.5 1 24 1 14.82 1 7.07 6.48 3.58 14.22l7.1 5.52C12.4 13.35 17.72 9.5 24 9.5z"/>
              <path fill="#4285F4" d="M46.52 24.5c0-1.64-.15-3.22-.42-4.75H24v9h12.67c-.55 2.97-2.2 5.48-4.68 7.18l7.18 5.58C43.27 37.28 46.52 31.37 46.52 24.5z"/>
              <path fill="#FBBC05" d="M10.68 28.26A14.56 14.56 0 0 1 9.5 24c0-1.48.25-2.91.68-4.26l-7.1-5.52A23.94 23.94 0 0 0 0 24c0 3.86.92 7.5 2.54 10.72l8.14-6.46z"/>
              <path fill="#34A853" d="M24 47c5.5 0 10.12-1.82 13.5-4.95l-7.18-5.58c-1.83 1.23-4.17 1.96-6.32 1.96-6.28 0-11.6-3.85-13.32-9.17l-8.14 6.46C7.07 41.52 14.82 47 24 47z"/>
            </svg>
            Google 계정으로 가입
          </button>
          {googleError && <p style={{ color: 'var(--danger, #e53e3e)', fontSize: 13, textAlign: 'center', marginBottom: 8 }}>{googleError}</p>}

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '16px 0' }}>
            <div style={{ flex: 1, height: 1, background: 'var(--border, #e2e8f0)' }} />
            <span className="t-caption" style={{ color: 'var(--color-text-2)', whiteSpace: 'nowrap' }}>또는 이메일로 가입</span>
            <div style={{ flex: 1, height: 1, background: 'var(--border, #e2e8f0)' }} />
          </div>

          <form onSubmit={handleSubmit}>
            <div className="stack" style={{ marginTop: 28, ['--gap' as string]: '14px' }}>
              <div className="field">
                <label className="field-label">사용자명</label>
                <input
                  className={`input${errors.username ? ' input-error' : ''}`}
                  placeholder="2자 이상"
                  value={form.username}
                  onChange={set('username')}
                  onBlur={handleUsernameBlur}
                  required
                />
                {errors.username && <span className="field-error">{errors.username}</span>}
              </div>
              <div className="field">
                <label className="field-label">이메일</label>
                <input
                  className={`input${errors.email ? ' input-error' : ''}`}
                  type="email"
                  placeholder="you@email.com"
                  value={form.email}
                  onChange={set('email')}
                  onBlur={handleEmailBlur}
                  required
                />
                {errors.email && <span className="field-error">{errors.email}</span>}
              </div>
              <div className="field">
                <label className="field-label">비밀번호</label>
                <input
                  className={`input${errors.password ? ' input-error' : ''}`}
                  type="password"
                  placeholder="8자 이상"
                  value={form.password}
                  onChange={set('password')}
                  required
                />
                {errors.password
                  ? <span className="field-error">{errors.password}</span>
                  : <span className="field-hint">영문, 숫자, 특수문자 조합 권장</span>
                }
              </div>
              <div className="field">
                <label className="field-label">비밀번호 확인</label>
                <input
                  className={`input${errors.confirm ? ' input-error' : ''}`}
                  type="password"
                  value={form.confirm}
                  onChange={set('confirm')}
                  required
                />
                {errors.confirm && <span className="field-error">{errors.confirm}</span>}
              </div>
              {errors.form && (
                <div className="alert is-error">{errors.form}</div>
              )}
              <button
                type="submit"
                className="btn btn-primary btn-lg"
                style={{ width: '100%', marginTop: 4 }}
                disabled={loading}
              >
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
