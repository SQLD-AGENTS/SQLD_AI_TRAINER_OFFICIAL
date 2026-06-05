const CHAPTERS = [
  'SQL 기본', 'JOIN 심화', '인덱스 튜닝', '서브쿼리',
  '트랜잭션', '정규화', '윈도우 함수', '옵티마이저',
  'DDL/DML', '제약조건', 'PL/SQL', '함수/집계',
];

const DIFFICULTIES = ['전체', 'Easy', 'Medium', 'Hard'];
const TYPES = ['전체', 'best_choice', 'worst_choice', 'fill_blank', 'different_result'];

export interface Filters {
  chapters: string[];
  difficulty: string;
  question_type: string;
}

interface Props {
  filters: Filters;
  onChange: (f: Filters) => void;
  onReset: () => void;
}

export default function FilterPanel({ filters, onChange, onReset }: Props) {
  const toggleChapter = (ch: string) => {
    const next = filters.chapters.includes(ch)
      ? filters.chapters.filter((c) => c !== ch)
      : [...filters.chapters, ch];
    onChange({ ...filters, chapters: next });
  };

  return (
    <div className="card card-pad-sm">
      <div className="stack" style={{ ['--gap' as string]: '20px' }}>
        <div>
          <div className="t-caption-b" style={{
            marginBottom: 6, textTransform: 'uppercase',
            letterSpacing: '0.05em', fontSize: 11, color: 'var(--text-3)',
          }}>챕터</div>
          {CHAPTERS.map((ch) => (
            <div
              key={ch}
              className={`opt-row${filters.chapters.includes(ch) ? ' is-on' : ''}`}
              onClick={() => toggleChapter(ch)}
            >
              <div className="box">{filters.chapters.includes(ch) ? '✓' : ''}</div>
              {ch}
            </div>
          ))}
        </div>

        <div>
          <div className="t-caption-b" style={{
            marginBottom: 6, textTransform: 'uppercase',
            letterSpacing: '0.05em', fontSize: 11, color: 'var(--text-3)',
          }}>난이도</div>
          {DIFFICULTIES.map((d) => (
            <div
              key={d}
              className={`opt-row${filters.difficulty === d ? ' is-on' : ''}`}
              onClick={() => onChange({ ...filters, difficulty: d })}
            >
              <div className="dot" />
              {d}
            </div>
          ))}
        </div>

        <div>
          <div className="t-caption-b" style={{
            marginBottom: 6, textTransform: 'uppercase',
            letterSpacing: '0.05em', fontSize: 11, color: 'var(--text-3)',
          }}>문제 유형</div>
          {TYPES.map((t) => (
            <div
              key={t}
              className={`opt-row${filters.question_type === t ? ' is-on' : ''}`}
              onClick={() => onChange({ ...filters, question_type: t })}
            >
              <div className="dot" />
              {t}
            </div>
          ))}
        </div>

        <button className="btn btn-outline btn-sm" style={{ width: '100%' }} onClick={onReset}>
          초기화
        </button>
      </div>
    </div>
  );
}
