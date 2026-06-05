import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import PageLayout from '../components/layout/PageLayout';
import FilterPanel, { type Filters } from '../components/question/FilterPanel';
import QuestionCard from '../components/question/QuestionCard';
import Spinner from '../components/ui/Spinner';
import { questionsApi } from '../services/api';

const DEFAULT_FILTERS: Filters = { chapters: [], difficulty: '전체', question_type: '전체' };

export default function QuestionListPage() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);

  const PAGE_SIZE = 12;
  const params = {
    ...(filters.chapters.length > 0 && { chapter_name: filters.chapters.join(',') }),
    ...(filters.difficulty !== '전체' && { difficulty: filters.difficulty }),
    ...(filters.question_type !== '전체' && { question_type: filters.question_type }),
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };

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
      setFilters((f) => ({ ...f, chapters: f.chapters.filter((c) => c !== label) }));
    } else if (label === filters.difficulty) {
      setFilters((f) => ({ ...f, difficulty: '전체' }));
    } else {
      setFilters((f) => ({ ...f, question_type: '전체' }));
    }
  };

  return (
    <PageLayout wide>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 20 }}>
        <div>
          <h1 className="t-h1">문제 목록</h1>
          <p className="t-body-2" style={{ margin: '6px 0 0' }}>
            {data ? `총 ${data.total}문제` : '로딩 중…'} · 필터 결과{' '}
            <strong style={{ color: 'var(--text)' }}>{total}문제</strong>
          </p>
        </div>
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
            onClick={() => { setFilters(DEFAULT_FILTERS); setPage(1); }}
          >
            모두 지우기
          </button>
        </div>
      )}

      <div className="row" style={{ alignItems: 'flex-start', gap: 24 }}>
        <aside style={{ width: 240, flexShrink: 0 }}>
          <FilterPanel
            filters={filters}
            onChange={(f) => { setFilters(f); setPage(1); }}
            onReset={() => { setFilters(DEFAULT_FILTERS); setPage(1); }}
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
                <QuestionCard key={q.question_id} q={q} />
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <div className="pager" style={{ marginTop: 24 }}>
              <span className={`p${page === 1 ? ' is-dis' : ''}`} onClick={() => page > 1 && setPage(page - 1)}>‹</span>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                <span key={p} className={`p${p === page ? ' is-active' : ''}`} onClick={() => setPage(p)}>{p}</span>
              ))}
              <span className={`p${page === totalPages ? ' is-dis' : ''}`} onClick={() => page < totalPages && setPage(page + 1)}>›</span>
            </div>
          )}
        </main>
      </div>
    </PageLayout>
  );
}
