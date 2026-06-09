import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { profileApi } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import DeleteAccountModal from './DeleteAccountModal';

export default function ProfileDangerZone() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [showModal, setShowModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  function handleLogout() {
    logout();
    navigate('/');
  }

  async function handleDeleteConfirm() {
    setDeleting(true);
    setError('');
    try {
      await profileApi.deleteMe();
      logout();
      navigate('/');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? '탈퇴 처리에 실패했습니다. 다시 시도해 주세요.');
      setDeleting(false);
    }
  }

  return (
    <section style={{ maxWidth: 480 }}>
      <h2 style={{ marginTop: 0, marginBottom: 8, fontSize: 18, color: 'var(--danger, #e53e3e)' }}>위험 영역</h2>
      <p style={{ margin: '0 0 24px', fontSize: 13, color: 'var(--text-2)' }}>아래 작업들은 되돌리기 어렵습니다. 신중하게 진행하세요.</p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ padding: '20px 24px', border: '1px solid var(--border, #e2e8f0)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>이 기기 로그아웃</p>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-2)' }}>현재 기기에서 로그아웃합니다.</p>
          </div>
          <button className="btn btn-outline btn-sm" onClick={handleLogout} style={{ flexShrink: 0 }}>
            로그아웃
          </button>
        </div>

        <div style={{ padding: '20px 24px', border: '1px solid var(--border, #e2e8f0)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, opacity: 0.5 }}>
          <div>
            <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>모든 기기 로그아웃</p>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-2)' }}>JWT stateless 구조로 현재 미지원입니다.</p>
          </div>
          <button className="btn btn-outline btn-sm" disabled title="현재 미지원" style={{ flexShrink: 0, cursor: 'not-allowed' }}>
            미지원
          </button>
        </div>

        <div style={{ padding: '20px 24px', border: '1px solid var(--danger, #e53e3e)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>회원 탈퇴</p>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-2)' }}>계정이 비활성화됩니다. 재가입이 제한될 수 있습니다.</p>
          </div>
          <button
            className="btn btn-sm"
            style={{ background: 'var(--danger, #e53e3e)', color: '#fff', border: 'none', flexShrink: 0 }}
            onClick={() => setShowModal(true)}
          >
            탈퇴
          </button>
        </div>
      </div>

      {error && <p style={{ marginTop: 16, color: 'var(--danger, #e53e3e)', fontSize: 13 }}>{error}</p>}

      {showModal && (
        <DeleteAccountModal
          onConfirm={handleDeleteConfirm}
          onCancel={() => { if (!deleting) setShowModal(false); }}
          loading={deleting}
        />
      )}
    </section>
  );
}
