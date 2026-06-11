interface DeleteAccountModalProps {
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

export default function DeleteAccountModal({ onConfirm, onCancel, loading }: DeleteAccountModalProps) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={onCancel}
    >
      <div
        style={{
          background: 'var(--surface, #fff)', borderRadius: 16, padding: 32,
          maxWidth: 420, width: '90%', boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 18 }}>회원 탈퇴</h3>
        <p style={{ fontSize: 14, color: 'var(--text-2)', marginBottom: 8 }}>
          정말로 탈퇴하시겠습니까? 이 작업은 되돌릴 수 없습니다.
        </p>
        <p style={{ fontSize: 13, color: 'var(--danger, #e53e3e)', marginBottom: 24, padding: '10px 14px', background: 'rgba(229,62,62,0.08)', borderRadius: 8 }}>
          탈퇴 후 동일한 이메일로 재가입이 제한될 수 있습니다.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button className="btn btn-outline" onClick={onCancel} disabled={loading}>취소</button>
          <button
            className="btn"
            style={{ background: 'var(--danger, #e53e3e)', color: '#fff', border: 'none' }}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? '탈퇴 중...' : '탈퇴하기'}
          </button>
        </div>
      </div>
    </div>
  );
}
