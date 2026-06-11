import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { profileApi, progressApi } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

interface Stats {
  createdAt: string;
  totalAttempts: number | null;
  overallAccuracy: number | null;
  streak: number | null;
}

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });
}

export default function ProfileStats() {
  const { user } = useAuth();
  const [stats, setStats] = useState<Stats>({ createdAt: '', totalAttempts: null, overallAccuracy: null, streak: null });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      profileApi.getMe(),
      progressApi.get(user.user_id),
    ]).then(([meRes, progressRes]) => {
      const me = meRes.data;
      const prog = progressRes.data as { total_attempts?: number; overall_accuracy?: number; streak_days?: number };
      setStats({
        createdAt: me.created_at ?? '',
        totalAttempts: prog.total_attempts ?? null,
        overallAccuracy: prog.overall_accuracy ?? null,
        streak: prog.streak_days ?? null,
      });
    }).catch(() => {
      // 통계 로드 실패 시 빈 상태 유지
    }).finally(() => setLoading(false));
  }, [user]);

  if (loading) return <p style={{ color: 'var(--text-2)' }}>불러오는 중...</p>;

  const cards = [
    { label: '가입일', value: formatDate(stats.createdAt) },
    { label: '총 시도', value: stats.totalAttempts !== null ? `${stats.totalAttempts}회` : '-' },
    { label: '전체 정답률', value: stats.overallAccuracy !== null ? `${(stats.overallAccuracy * 100).toFixed(1)}%` : '-' },
    { label: '연속 학습', value: stats.streak !== null ? `${stats.streak}일` : '-' },
  ];

  return (
    <section>
      <h2 style={{ marginTop: 0, marginBottom: 24, fontSize: 18 }}>계정 통계</h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 16, marginBottom: 32 }}>
        {cards.map((c) => (
          <div key={c.label} style={{ background: 'var(--surface-2, #f7f7f7)', borderRadius: 12, padding: '20px 24px' }}>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-2)', marginBottom: 8 }}>{c.label}</p>
            <p style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>{c.value}</p>
          </div>
        ))}
      </div>

      <Link to="/dashboard">
        <button className="btn btn-outline btn-sm">대시보드 보기</button>
      </Link>
    </section>
  );
}
