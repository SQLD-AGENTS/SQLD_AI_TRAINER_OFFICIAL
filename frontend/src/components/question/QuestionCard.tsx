import { Link } from 'react-router-dom';
import DifficultyBadge from '../ui/DifficultyBadge';

interface Question {
  question_id: string;
  question_text: string;
  chapter_name: string;
  difficulty_label?: string | null;
  question_type?: string | null;
  has_sql?: boolean | null;
  attempt_count?: number;
  accuracy?: number;
}

interface QuestionCardProps {
  q: Question;
  isSolved?: boolean;
  isCorrect?: boolean;
}

export default function QuestionCard({ q, isSolved, isCorrect }: QuestionCardProps) {
  const borderLeft = isCorrect
    ? '4px solid var(--success)'
    : isSolved
    ? '4px solid var(--warning)'
    : undefined;

  return (
    <div className="card card-pad-sm" style={{
      cursor: 'pointer', borderLeft, position: 'relative',
      display: 'flex', flexDirection: 'column',
      minHeight: 150,
    }}>
      {isCorrect && (
        <span style={{
          position: 'absolute', top: 10, right: 12,
          color: 'var(--success)', fontSize: 12, fontWeight: 700,
          background: 'rgba(16, 185, 129, 0.12)',
          border: '1px solid var(--success)',
          padding: '2px 8px', borderRadius: 99,
        }}>
          ✓ 해결
        </span>
      )}
      {isSolved && !isCorrect && (
        <span style={{
          position: 'absolute', top: 10, right: 12,
          color: 'var(--warning)', fontSize: 12, fontWeight: 600,
          background: 'rgba(245, 158, 11, 0.12)',
          border: '1px solid var(--warning)',
          padding: '2px 8px', borderRadius: 99,
        }}>
          재도전
        </span>
      )}
      <div className="row gap-6" style={{ flexWrap: 'wrap' }}>
        <span className="tag is-light">{q.chapter_name}</span>
        {q.difficulty_label && <DifficultyBadge difficulty={q.difficulty_label} />}
        {q.question_type && <span className="tag">{q.question_type}</span>}
        {q.has_sql && <span className="tag">SQL</span>}
      </div>
      <div style={{ flex: 1, marginTop: 12, overflow: 'hidden' }}>
        <p className="t-body" style={{
          margin: 0, fontSize: 15,
          display: '-webkit-box', WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {q.question_text}
        </p>
      </div>
      <div className="row" style={{ justifyContent: 'space-between', marginTop: 16 }}>
        <span className="t-caption">
          #{q.question_id}
          {q.attempt_count !== undefined && ` · 시도 ${q.attempt_count}회`}
          {q.accuracy !== undefined && ` · 정답률 ${Math.round(q.accuracy * 100)}%`}
        </span>
        <Link to={`/questions/${q.question_id}`} className="link-pill">
          풀기 ›
        </Link>
      </div>
    </div>
  );
}
