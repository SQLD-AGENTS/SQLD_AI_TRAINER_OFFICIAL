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

export default function QuestionCard({ q }: { q: Question }) {
  return (
    <div className="card card-pad-sm" style={{ cursor: 'pointer' }}>
      <div className="row gap-6" style={{ flexWrap: 'wrap' }}>
        <span className="tag is-light">{q.chapter_name}</span>
        {q.difficulty_label && <DifficultyBadge difficulty={q.difficulty_label} />}
        {q.question_type && <span className="tag">{q.question_type}</span>}
        {q.has_sql && <span className="tag">SQL</span>}
      </div>
      <p className="t-body" style={{
        marginTop: 12, marginBottom: 0, fontSize: 15,
        display: '-webkit-box', WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical', overflow: 'hidden',
      }}>
        {q.question_text}
      </p>
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
