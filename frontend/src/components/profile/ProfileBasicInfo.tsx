import { useState } from 'react';
import { profileApi } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import Avatar from '../ui/Avatar';

export default function ProfileBasicInfo() {
  const { user, updateUsername } = useAuth();
  const [username, setUsername] = useState(user?.username ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isDirty = username !== (user?.username ?? '');

  async function handleSave() {
    if (!isDirty) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await profileApi.updateMe({ username });
      updateUsername(username);
      setSuccess('저장되었습니다.');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? '저장에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <h2 style={{ marginTop: 0, marginBottom: 4, fontSize: 18, fontWeight: 600 }}>기본 정보</h2>
      <p style={{ margin: '0 0 28px', fontSize: 13, color: 'var(--text-2)' }}>프로필 사진, 사용자명, 이메일을 변경합니다.</p>

      {/* 프로필 사진 */}
      <div style={{ marginBottom: 28 }}>
        <p style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 500 }}>프로필 사진</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <Avatar username={username || user?.username || '?'} size={72} fontSize={28} />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <button
                className="btn btn-outline btn-sm"
                disabled
                title="추후 지원 예정"
                style={{ cursor: 'not-allowed', opacity: 0.5 }}
              >
                이미지 변경
              </button>
              <button
                className="btn-ghost btn-sm"
                disabled
                title="추후 지원 예정"
                style={{ cursor: 'not-allowed', opacity: 0.5, background: 'none', border: 'none', fontSize: 13, color: 'var(--text-2)', padding: '5px 4px' }}
              >
                삭제
              </button>
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
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>중복 확인</span>
        </div>
        <input className="input" value={user?.email ?? ''} readOnly style={{ background: 'var(--surface-2)', color: 'var(--text-2)', cursor: 'not-allowed' }} />
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
          disabled={!isDirty || saving}
        >
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </section>
  );
}
