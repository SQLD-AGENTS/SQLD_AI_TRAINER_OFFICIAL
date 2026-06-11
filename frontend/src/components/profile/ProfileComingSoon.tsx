interface ProfileComingSoonProps {
  label: string;
}

export default function ProfileComingSoon({ label }: ProfileComingSoonProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 24px', gap: 12, color: 'var(--text-2)' }}>
      <div style={{ fontSize: 40 }}>🚧</div>
      <p style={{ margin: 0, fontWeight: 600, fontSize: 16 }}>{label} — 준비 중</p>
      <p style={{ margin: 0, fontSize: 14 }}>이 기능은 곧 제공될 예정입니다.</p>
    </div>
  );
}
