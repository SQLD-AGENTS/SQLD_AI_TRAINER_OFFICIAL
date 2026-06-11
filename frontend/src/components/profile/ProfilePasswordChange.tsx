import { useState, useEffect } from 'react';
import { profileApi } from '../../services/api';

function getStrengthLabel(pw: string): { label: string; color: string } {
  if (pw.length === 0) return { label: '', color: '' };
  if (pw.length < 8) return { label: '약함 (8자 미만)', color: 'var(--danger, #e53e3e)' };
  if (/[^A-Za-z0-9]/.test(pw)) return { label: '강함 (특수문자 포함)', color: 'var(--success, #38a169)' };
  return { label: '보통 (8자 이상)', color: 'var(--warning, #d69e2e)' };
}

export default function ProfilePasswordChange() {
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isSocialOnly, setIsSocialOnly] = useState(false);
  const [hasPassword, setHasPassword] = useState(true);
  const [profileLoading, setProfileLoading] = useState(true);

  useEffect(() => {
    profileApi.getMe().then((res) => {
      const profile = res.data;
      const social = !!profile.social_provider;
      setIsSocialOnly(social);
      setHasPassword(!social);
    }).catch(() => {}).finally(() => setProfileLoading(false));
  }, []);

  const strength = getStrengthLabel(newPw);
  const mismatch = confirmPw.length > 0 && newPw !== confirmPw;

  async function handleSave() {
    if (!currentPw) { setError('현재 비밀번호를 입력해주세요.'); return; }
    if (newPw !== confirmPw) { setError('새 비밀번호가 일치하지 않습니다.'); return; }
    if (newPw.length < 8) { setError('비밀번호는 8자 이상이어야 합니다.'); return; }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await profileApi.updateMe({ password: newPw, current_password: currentPw });
      setSuccess('비밀번호가 변경되었습니다.');
      setCurrentPw('');
      setNewPw('');
      setConfirmPw('');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? '변경에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  }

  if (profileLoading) return <section style={{ minHeight: 200 }} />;

  if (isSocialOnly) {
    return (
      <section style={{ maxWidth: 480 }}>
        <h2 style={{ marginTop: 0, marginBottom: 8, fontSize: 18 }}>비밀번호 변경</h2>
        <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--text-2)' }}>
          구글 소셜 로그인 계정은 비밀번호 변경이 불가합니다.
        </p>
        <div style={{ padding: '14px 16px', background: 'var(--surface-2, #f7fafc)', borderRadius: 8, fontSize: 13, color: 'var(--text-3)' }}>
          소셜 계정으로 가입하셨습니다. Google 계정 설정에서 비밀번호를 관리해주세요.
        </div>
      </section>
    );
  }

  return (
    <section style={{ maxWidth: 480 }}>
      <h2 style={{ marginTop: 0, marginBottom: 8, fontSize: 18 }}>비밀번호 변경</h2>
      <p style={{ margin: '0 0 24px', fontSize: 13, color: 'var(--text-2)' }}>
        {hasPassword ? '현재 비밀번호 확인 후 새 비밀번호로 변경합니다.' : '소셜 계정에 비밀번호를 새로 설정합니다.'}
      </p>

      {hasPassword && <div className="form-group" style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 500 }}>
          현재 비밀번호
        </label>
        <input
          className="input"
          type="password"
          value={currentPw}
          onChange={(e) => { setCurrentPw(e.target.value); setError(''); setSuccess(''); }}
          placeholder="현재 비밀번호 입력"
        />
      </div>}

      <div className="form-group" style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 500 }}>새 비밀번호</label>
        <input
          className="input"
          type="password"
          value={newPw}
          onChange={(e) => { setNewPw(e.target.value); setError(''); setSuccess(''); }}
          placeholder="새 비밀번호 입력 (8자 이상)"
        />
        {strength.label && (
          <p style={{ margin: '4px 0 0', fontSize: 12, color: strength.color }}>{strength.label}</p>
        )}
      </div>

      <div className="form-group" style={{ marginBottom: 24 }}>
        <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 500 }}>새 비밀번호 확인</label>
        <input
          className="input"
          type="password"
          value={confirmPw}
          onChange={(e) => { setConfirmPw(e.target.value); setError(''); setSuccess(''); }}
          placeholder="새 비밀번호 재입력"
          style={mismatch ? { borderColor: 'var(--danger, #e53e3e)' } : {}}
        />
        {mismatch && (
          <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--danger, #e53e3e)' }}>비밀번호가 일치하지 않습니다.</p>
        )}
      </div>

      {error && <p style={{ color: 'var(--danger, #e53e3e)', fontSize: 13, marginBottom: 12 }}>{error}</p>}
      {success && <p style={{ color: 'var(--success, #38a169)', fontSize: 13, marginBottom: 12 }}>{success}</p>}

      <button
        className="btn btn-primary"
        onClick={handleSave}
        disabled={saving || (hasPassword && !currentPw) || !newPw || !confirmPw || mismatch}
      >
        {saving ? '변경 중...' : '비밀번호 변경'}
      </button>
    </section>
  );
}
