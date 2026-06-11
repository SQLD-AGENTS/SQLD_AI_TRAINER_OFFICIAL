import { useEffect, useRef, useState } from 'react';
import { profileApi, BASE_URL } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import Avatar from '../ui/Avatar';

type EmailCheckState = 'idle' | 'checking' | 'available' | 'taken';

function resolveUrl(url: string | null): string | null {
  if (!url) return null;
  return url.startsWith('http://') || url.startsWith('https://') ? url : `${BASE_URL}${url}`;
}

export default function ProfileBasicInfo() {
  const { user, updateUsername, updateAvatarUrl } = useAuth();
  const [username, setUsername] = useState(user?.username ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [pendingAvatarFile, setPendingAvatarFile] = useState<File | null>(null);
  const [previewAvatarUrl, setPreviewAvatarUrl] = useState<string | null>(null);
  const [pendingAvatarDelete, setPendingAvatarDelete] = useState(false);
  const [emailCheck, setEmailCheck] = useState<EmailCheckState>('idle');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const originalUsername = user?.username ?? '';
  const originalEmail = user?.email ?? '';
  const emailChanged = email !== originalEmail;
  const avatarDirty = pendingAvatarFile !== null || pendingAvatarDelete;
  const isDirty = username !== originalUsername || emailChanged || avatarDirty;

  // 프로필 조회로 avatar_url 로드 및 context 동기화
  useEffect(() => {
    profileApi.getMe().then((res) => {
      const url = res.data.avatar_url ?? null;
      setAvatarUrl(url);
      updateAvatarUrl(resolveUrl(url));
    }).catch(() => {});
  }, []);

  // previewAvatarUrl 메모리 누수 방지
  useEffect(() => {
    return () => {
      if (previewAvatarUrl) URL.revokeObjectURL(previewAvatarUrl);
    };
  }, [previewAvatarUrl]);

  // 이메일이 바뀌면 중복 확인 상태 초기화
  useEffect(() => {
    setEmailCheck('idle');
  }, [email]);

  async function handleCheckEmail() {
    if (!emailChanged) return;
    setEmailCheck('checking');
    try {
      const res = await profileApi.checkEmail(email);
      setEmailCheck(res.data.available ? 'available' : 'taken');
    } catch {
      setEmailCheck('idle');
    }
  }

  async function handleSave() {
    if (!isDirty) return;
    if (emailChanged && emailCheck === 'taken') {
      setError('이미 사용 중인 이메일입니다.');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      // 텍스트 필드 저장
      const payload: { username?: string; email?: string } = {};
      if (username !== originalUsername) payload.username = username;
      if (emailChanged) payload.email = email;
      if (Object.keys(payload).length > 0) await profileApi.updateMe(payload);
      if (username !== originalUsername) updateUsername(username);

      // 아바타 업로드
      if (pendingAvatarFile) {
        const res = await profileApi.uploadAvatar(pendingAvatarFile);
        const rawUrl = res.data.avatar_url ?? null;
        setAvatarUrl(rawUrl);
        updateAvatarUrl(resolveUrl(rawUrl));
        setPendingAvatarFile(null);
        if (previewAvatarUrl) URL.revokeObjectURL(previewAvatarUrl);
        setPreviewAvatarUrl(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      }

      // 아바타 삭제
      if (pendingAvatarDelete) {
        await profileApi.deleteAvatar();
        setAvatarUrl(null);
        updateAvatarUrl(null);
        setPendingAvatarDelete(false);
      }

      setSuccess('저장되었습니다.');
      setEmailCheck('idle');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? '저장에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  }

  function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (previewAvatarUrl) URL.revokeObjectURL(previewAvatarUrl);
    setPendingAvatarFile(file);
    setPreviewAvatarUrl(URL.createObjectURL(file));
    setPendingAvatarDelete(false);
    setSuccess('');
    setError('');
  }

  function handleAvatarDelete() {
    if (previewAvatarUrl) URL.revokeObjectURL(previewAvatarUrl);
    setPendingAvatarFile(null);
    setPreviewAvatarUrl(null);
    setPendingAvatarDelete(true);
    setSuccess('');
    setError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  const displayAvatarUrl = previewAvatarUrl ?? resolveUrl(avatarUrl);
  const hasAvatar = previewAvatarUrl !== null || (avatarUrl !== null && !pendingAvatarDelete);

  const emailHint = emailChanged
    ? emailCheck === 'available'
      ? <span style={{ fontSize: 12, color: 'var(--success, #38a169)' }}>사용 가능</span>
      : emailCheck === 'taken'
        ? <span style={{ fontSize: 12, color: 'var(--danger, #e53e3e)' }}>이미 사용 중</span>
        : (
          <button
            type="button"
            onClick={handleCheckEmail}
            disabled={emailCheck === 'checking'}
            style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
          >
            {emailCheck === 'checking' ? '확인 중...' : '중복 확인'}
          </button>
        )
    : <span style={{ fontSize: 12, color: 'var(--text-3)' }}>중복 확인</span>;

  return (
    <section>
      <h2 style={{ marginTop: 0, marginBottom: 4, fontSize: 18, fontWeight: 600 }}>기본 정보</h2>
      <p style={{ margin: '0 0 28px', fontSize: 13, color: 'var(--text-2)' }}>프로필 사진, 사용자명, 이메일을 변경합니다.</p>

      {/* 프로필 사진 */}
      <div style={{ marginBottom: 28 }}>
        <p style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 500 }}>프로필 사진</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <Avatar username={username || user?.username || '?'} size={72} fontSize={28} imageUrl={displayAvatarUrl} />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png"
                style={{ display: 'none' }}
                onChange={handleAvatarChange}
              />
              <button
                className="btn btn-outline btn-sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={saving}
              >
                이미지 변경
              </button>
              {hasAvatar && (
                <button
                  type="button"
                  onClick={handleAvatarDelete}
                  style={{ background: 'none', border: 'none', fontSize: 13, color: 'var(--text-2)', cursor: 'pointer', padding: '5px 4px' }}
                >
                  삭제
                </button>
              )}
            </div>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-3)' }}>JPG, PNG · 최대 2MB</p>
          </div>
        </div>
      </div>

      {/* 회원 ID */}
      <div className="form-group" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <label style={{ fontSize: 13, fontWeight: 500 }}>회원 ID</label>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>변경 불가</span>
        </div>
        <input className="input" value={user?.user_id ?? ''} readOnly style={{ background: 'var(--surface-2)', color: 'var(--text-2)', cursor: 'not-allowed' }} />
      </div>

      {/* 사용자명 */}
      <div className="form-group" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <label style={{ fontSize: 13, fontWeight: 500 }}>사용자명</label>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>2-20자</span>
        </div>
        <input
          className="input"
          value={username}
          onChange={(e) => { setUsername(e.target.value); setSuccess(''); setError(''); }}
          maxLength={20}
        />
      </div>

      {/* 이메일 */}
      <div className="form-group" style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <label style={{ fontSize: 13, fontWeight: 500 }}>이메일</label>
          {emailHint}
        </div>
        <input
          className="input"
          type="email"
          value={email}
          onChange={(e) => { setEmail(e.target.value); setSuccess(''); setError(''); }}
        />
      </div>

      {error && <p style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 12 }}>{error}</p>}
      {success && <p style={{ color: 'var(--success)', fontSize: 13, marginBottom: 12 }}>{success}</p>}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 14, color: 'var(--text-3)' }}>
          {!isDirty && '변경 사항 없음'}
        </span>
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={!isDirty || saving || emailCheck === 'taken'}
        >
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </section>
  );
}
