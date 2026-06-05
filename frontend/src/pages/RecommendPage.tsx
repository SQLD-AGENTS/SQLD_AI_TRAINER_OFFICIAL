import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import PageLayout from '../components/layout/PageLayout';
import RecommendCard from '../components/recommend/RecommendCard';
import AiBadge from '../components/ui/AiBadge';
import Spinner from '../components/ui/Spinner';
import { recommendApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

export default function RecommendPage() {
  const { user } = useAuth();
  const [useZpd, setUseZpd] = useState(true);
  const [topN, setTopN] = useState(10);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['recommend', user?.user_id, topN, useZpd],
    queryFn: () => recommendApi.get(user!.user_id, topN, useZpd).then((r) => r.data),
    enabled: !!user,
  });

  const questions = data?.recommendations ?? [];
  const weakChapters: string[] = data?.weak_chapters ?? [];
  const zpdCount: number = data?.zpd_count ?? 0;

  return (
    <PageLayout wide>
      <div style={{ marginBottom: 20 }}>
        <AiBadge>DKT 하이브리드 추천</AiBadge>
        <h1 className="t-h1" style={{ marginTop: 6 }}>AI 맞춤 추천</h1>
        <p className="t-body-2" style={{ marginTop: 6, maxWidth: 720 }}>
          Deep Knowledge Tracing 모델이 당신의 풀이 이력을 분석해, 지금 가장 학습 효율이 높은 문제를 골랐습니다.
          ZPD 필터를 켜면 근접발달영역(P(correct) 0.3~0.6) 문제만 보여줍니다.
        </p>
      </div>

      <div className="card" style={{ padding: 16 }}>
        <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
          <div className="row gap-24">
            <div className="row gap-8">
              <span className="t-body-2" style={{ color: 'var(--text)' }}>ZPD 필터</span>
              <button
                className={`toggle${useZpd ? '' : ' is-off'}`}
                onClick={() => setUseZpd((v) => !v)}
              />
            </div>
            <div className="row gap-8">
              <span className="t-body-2" style={{ color: 'var(--text)' }}>상위 N개</span>
              <select
                className="btn btn-outline btn-sm"
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
                style={{ cursor: 'pointer' }}
              >
                {[5, 10, 20].map((n) => <option key={n} value={n}>{n}개</option>)}
              </select>
            </div>
          </div>
          <button className="btn btn-primary" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? <Spinner size="sm" /> : '새 추천 받기'}
          </button>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h3 className="t-h3">취약 챕터 분석</h3>
          <p className="t-caption" style={{ marginTop: 4 }}>weak_chapters · 최근 50회 풀이 기반</p>
          <div className="row gap-8" style={{ marginTop: 14, flexWrap: 'wrap' }}>
            {weakChapters.length === 0 ? (
              <span className="t-caption">데이터 없음</span>
            ) : (
              weakChapters.map((ch) => (
                <span key={ch} className="tag">
                  <span className="dot" style={{ background: 'var(--danger)' }} />
                  {ch}
                </span>
              ))
            )}
          </div>
        </div>
        <div className="card" style={{ background: 'linear-gradient(180deg, var(--ai-tint), var(--surface))', border: '1px solid #d0e3fa' }}>
          <AiBadge>ZPD 정보</AiBadge>
          <div className="row gap-24" style={{ marginTop: 12, alignItems: 'flex-end' }}>
            <div>
              <div className="t-caption">ZPD 범위 내 문제</div>
              <div style={{ fontSize: 28, fontWeight: 600, fontFeatureSettings: '"tnum"' }}>
                {zpdCount}<span className="t-caption" style={{ marginLeft: 4 }}>/ {topN}</span>
              </div>
            </div>
            <div className="sep-vert" style={{ height: 36 }} />
            <div>
              <div className="t-caption">P(correct) 범위</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--accent)', fontFeatureSettings: '"tnum"' }}>
                0.30 — 0.60
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="stack" style={{ marginTop: 20, ['--gap' as string]: '12px' }}>
        {isLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '48px 0' }}>
            <Spinner size="lg" />
          </div>
        ) : questions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '48px 0' }}>
            <p className="t-body-2" style={{ marginBottom: 16 }}>
              풀이 기록이 부족합니다. 문제를 더 풀면 정확한 추천이 제공됩니다.
            </p>
            <Link to="/questions">
              <button className="btn btn-primary">문제 풀러 가기</button>
            </Link>
          </div>
        ) : (
          questions.map((q: Omit<Parameters<typeof RecommendCard>[0], 'rank'>, i: number) => (
            <RecommendCard key={q.question_id} rank={i + 1} {...q} />
          ))
        )}
      </div>
    </PageLayout>
  );
}
