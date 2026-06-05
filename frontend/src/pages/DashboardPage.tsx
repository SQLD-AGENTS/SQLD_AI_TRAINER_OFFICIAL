import { useQuery } from '@tanstack/react-query';
import PageLayout from '../components/layout/PageLayout';
import SummaryCard from '../components/dashboard/SummaryCard';
import AccuracyChart from '../components/dashboard/AccuracyChart';
import WeakChapterList from '../components/dashboard/WeakChapterList';
import AiBadge from '../components/ui/AiBadge';
import Spinner from '../components/ui/Spinner';
import { progressApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { Link } from 'react-router-dom';

export default function DashboardPage() {
  const { user } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ['progress', user?.user_id],
    queryFn: () => progressApi.get(user!.user_id).then((r) => r.data),
    staleTime: 60 * 1000,
    enabled: !!user,
  });

  if (isLoading) {
    return (
      <PageLayout wide>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
          <Spinner size="lg" />
        </div>
      </PageLayout>
    );
  }

  const total_attempts = data?.total_attempts ?? 0;
  const overall_accuracy = data?.overall_accuracy ?? 0;
  const chapter_stats = data?.chapter_stats ?? [];
  const zpd_count = data?.zpd_available_count ?? 0;
  const weak_chapters = chapter_stats.filter((c: { accuracy: number }) => c.accuracy < 0.5);

  const accuracyColor = overall_accuracy >= 0.6 ? 'var(--success)' : 'var(--warning)';

  return (
    <PageLayout wide>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 20 }}>
        <div>
          <h1 className="t-h1">내 학습 현황</h1>
          <p className="t-body-2" style={{ margin: '6px 0 0' }}>최근 30일 학습 기록</p>
        </div>
      </div>

      <div className="grid-4">
        <SummaryCard
          label="총 시도"
          value={<>{total_attempts}<span style={{ fontSize: 18, color: 'var(--text-3)', marginLeft: 4 }}>회</span></>}
        />
        <SummaryCard
          label="전체 정답률"
          value={<>{(overall_accuracy * 100).toFixed(1)}<span style={{ fontSize: 18 }}>%</span></>}
          valueColor={accuracyColor}
          detail={`목표 70% 까지 -${Math.max(0, 70 - overall_accuracy * 100).toFixed(1)}%`}
        />
        <SummaryCard
          label="취약 챕터"
          value={<>{weak_chapters.length}<span style={{ fontSize: 18, color: 'var(--text-3)', marginLeft: 4 }}>개</span></>}
          valueColor={weak_chapters.length > 0 ? 'var(--danger)' : 'var(--success)'}
          detail="정답률 50% 미만"
        />
        <SummaryCard
          label={<AiBadge>ZPD 학습</AiBadge>}
          value={<>{zpd_count}<span style={{ fontSize: 18, color: 'var(--text-3)', marginLeft: 4 }}>개</span></>}
          valueColor="var(--accent)"
          detail="현재 풀기 적절한 문제"
          style={{ border: '1px solid #d0e3fa', background: 'linear-gradient(180deg, var(--ai-tint), var(--surface))' }}
        />
      </div>

      {chapter_stats.length > 0 && <AccuracyChart data={chapter_stats} />}

      <div className="grid-2" style={{ marginTop: 20 }}>
        <WeakChapterList chapters={chapter_stats} />

        <div className="card" style={{ background: 'linear-gradient(180deg, var(--ai-tint), var(--surface))', border: '1px solid #d0e3fa' }}>
          <AiBadge>ZPD 학습 가이드</AiBadge>
          <h3 className="t-h3" style={{ marginTop: 8 }}>당신에게 딱 맞는 {zpd_count}문제</h3>
          <p className="t-body-2" style={{ marginTop: 8 }}>
            DKT 모델이 예측한 정답 확률 0.3 ~ 0.6 구간의 문제입니다.
            너무 쉽지도 어렵지도 않은, 지금 풀어야 가장 학습 효율이 높은 문제들입니다.
          </p>
          <div style={{ marginTop: 16 }}>
            <div className="t-caption">예측 정답 확률 범위</div>
            <div className="bar-track" style={{ marginTop: 6 }}>
              <div className="bar-fill" style={{ width: '60%', background: 'linear-gradient(90deg, transparent 0%, var(--accent) 30%, var(--accent) 60%, transparent 90%)' }} />
            </div>
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 4 }}>
              <span className="t-caption">0.0</span>
              <span className="t-caption-b" style={{ color: 'var(--accent)' }}>0.3 — 0.6 (ZPD)</span>
              <span className="t-caption">1.0</span>
            </div>
          </div>
          <Link to="/recommend">
            <button className="btn btn-primary" style={{ marginTop: 18, width: '100%' }}>
              추천 문제 보러가기 ›
            </button>
          </Link>
        </div>
      </div>
    </PageLayout>
  );
}
