import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import PageLayout from '../components/layout/PageLayout';
import FilterPanel, { type Filters } from '../components/question/FilterPanel';
import QuestionCard from '../components/question/QuestionCard';
import Spinner from '../components/ui/Spinner';
import { questionsApi, logsApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const DEFAULT_FILTERS: Filters = { chapters: [], difficulty: '전체', question_type: '전체' };

function buildPageWindow(current: number, total: number): (number | '…')[] {
  if (total <= 9) return Array.from({ length: total }, (_, i) => i + 1);
  const delta = 2;
  const left = Math.max(2, current - delta);
  const right = Math.min(total - 1, current + delta);
  const pages: (number | '…')[] = [1];
  if (left > 2) pages.push('…');
  for (let i = left; i <= right; i++) pages.push(i);
  if (right < total - 1) pages.push('…');
  pages.push(total);
  return pages;
}

export default function QuestionListPage() {
  const { user, isGuest, showSolvedStatus, toggleShowSolvedStatus } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const filters: Filters = {
    chapters: searchParams.get('chapters')?.split(',').filter(Boolean) ?? [],
    difficulty: searchParams.get('difficulty') ?? '전체',
    question_type: searchParams.get('question_type') ?? '전체',
  };
  const page = Number(searchParams.get('page') ?? '1');

  const setFilters = (next: Filters) => {
    const p = new URLSearchParams();
    if (next.chapters.length > 0) p.set('chapters', next.chapters.join(','));
    if (next.difficulty !== '전체') p.set('difficulty', next.difficulty);
    if (next.question_type !== '전체') p.set('question_type', next.question_type);
    p.set('page', '1');
    setSearchParams(p, { replace: true });
  };

  const setPage = (n: number) => {
    const p = new URLSearchParams(searchParams);
    p.set('page', String(n));
    setSearchParams(p, { replace: true });
  };

  const PAGE_SIZE = 12;
  const params = {
    ...(filters.chapters.length > 0 && { chapter_name: filters.chapters.join(',') }),
    ...(filters.difficulty !== '전체' && { difficulty: filters.difficulty }),
    ...(filters.question_type !== '전체' && { question_type: filters.question_type }),
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };

  const { data: solvedData } = useQuery({
    queryKey: ['solved-summary'],
    queryFn: () => logsApi.getSolvedSummary().then((r) => r.data),
    enabled: !!user && !isGuest,
    staleTime: 60 * 1000,
  });

  const solvedSet = new Set(solvedData?.solved_ids ?? []);
  const correctSet = new Set(solvedData?.correct_ids ?? []);

  const { data, isLoading } = useQuery({
    queryKey: ['questions', params],
    queryFn: () => questionsApi.list(params).then((r) => r.data),
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error: any) => {
      const status = error?.response?.status;
      if (status === 502 || status === 503) return failureCount < 4;
      return false;
    },
    retryDelay: (attempt) => Math.min(2000 * (attempt + 1), 10000),
  });

  const questions = data?.questions ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

  const activeFilters = [
    ...filters.chapters,
    ...(filters.difficulty !== '전체' ? [filters.difficulty] : []),
    ...(filters.question_type !== '전체' ? [filters.question_type] : []),
  ];

  const removeFilter = (label: string) => {
    if (filters.chapters.includes(label)) {
      setFilters({ ...filters, chapters: filters.chapters.filter((c) => c !== label) });
    } else if (label === filters.difficulty) {
      setFilters({ ...filters, difficulty: '전체' });
    } else {
      setFilters({ ...filters, question_type: '전체' });
    }
  };

  return (
    <PageLayout wide>
      <div style={{ marginBottom: 20 }}>
        <h1 className="t-h1">문제 목록</h1>
        <p className="t-body-2" style={{ margin: '6px 0 0' }}>
          {data ? `총 ${data.total}문제` : '로딩 중…'} · 필터 결과{' '}
          <strong style={{ color: 'var(--text)' }}>{total}문제</strong>
        </p>
      </div>

      {activeFilters.length > 0 && (
        <div className="row gap-6" style={{ marginBottom: 20, flexWrap: 'wrap' }}>
          <span className="t-caption">필터:</span>
          {activeFilters.map((f) => (
            <span key={f} className="chip">
              {f}
              <span className="x" onClick={() => removeFilter(f)}>×</span>
            </span>
          ))}
          <button
            className="link-pill"
            style={{ marginLeft: 4, background: 'none', border: 'none', cursor: 'pointer' }}
            onClick={() => setFilters(DEFAULT_FILTERS)}
          >
            모두 지우기
          </button>
        </div>
      )}

      <div className="row" style={{ alignItems: 'flex-start', gap: 24 }}>
        <aside style={{ width: 240, flexShrink: 0 }}>
          {user && !isGuest && (
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                marginBottom: 12, cursor: 'pointer',
              }}
              onClick={toggleShowSolvedStatus}
            >
              <div className={`toggle${showSolvedStatus ? '' : ' is-off'}`} />
              <span className="t-body-2" style={{ userSelect: 'none' }}>풀이 여부 표시</span>
            </div>
          )}
          <FilterPanel
            filters={filters}
            onChange={setFilters}
            onReset={() => setFilters(DEFAULT_FILTERS)}
          />
        </aside>

        <main style={{ flex: 1 }}>
          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '48px 0' }}>
              <Spinner size="lg" />
            </div>
          ) : questions.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-3)' }}>
              조건에 맞는 문제가 없습니다.
            </div>
          ) : (
            <div className="grid-2">
              {questions.map((q: Parameters<typeof QuestionCard>[0]['q']) => (
                <QuestionCard
                  key={q.question_id}
                  q={q}
                  isSolved={showSolvedStatus ? solvedSet.has(q.question_id) : undefined}
                  isCorrect={showSolvedStatus ? correctSet.has(q.question_id) : undefined}
                />
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <div className="pager" style={{ marginTop: 24 }}>
              <span className={`p${page === 1 ? ' is-dis' : ''}`} onClick={() => page > 1 && setPage(page - 1)}>‹</span>
              {buildPageWindow(page, totalPages).map((p, idx) =>
                p === '…' ? (
                  <span key={`ellipsis-${idx}`} className="p" style={{ cursor: 'default' }}>…</span>
                ) : (
                  <span key={p} className={`p${p === page ? ' is-active' : ''}`} onClick={() => setPage(p)}>{p}</span>
                )
              )}
              <span className={`p${page === totalPages ? ' is-dis' : ''}`} onClick={() => page < totalPages && setPage(page + 1)}>›</span>
            </div>
          )}
        </main>
      </div>
    </PageLayout>
  );
}
