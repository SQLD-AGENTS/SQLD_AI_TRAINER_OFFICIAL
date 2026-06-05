import { Link } from 'react-router-dom';
import AiBadge from '../ui/AiBadge';
import Spinner from '../ui/Spinner';
import DifficultyBadge from '../ui/DifficultyBadge';

interface SimilarQuestion {
  question_id: number;
  question_text: string;
  chapter_name: string;
  difficulty: string;
}

interface Props {
  loading: boolean;
  explanation: string;
  similarQuestions: SimilarQuestion[];
}

export default function AiExplanation({ loading, explanation, similarQuestions }: Props) {
  return (
    <div className="ai-panel" style={{ marginTop: 16 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <AiBadge>RAG 기반 해설</AiBadge>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '32px 0' }}>
          <Spinner size="lg" />
        </div>
      ) : (
        <>
          <div className="t-body" style={{ fontSize: 15, color: 'var(--text-2)', marginTop: 16, lineHeight: 1.7 }}>
            {explanation}
          </div>

          {similarQuestions.length > 0 && (
            <>
              <div className="divider" />
              <h3 className="t-h3" style={{ marginBottom: 12 }}>유사 문제</h3>
              <div className="grid-3">
                {similarQuestions.slice(0, 3).map((sq) => (
                  <div key={sq.question_id} className="card card-pad-sm" style={{ cursor: 'pointer' }}>
                    <div className="row gap-6">
                      <span className="tag is-light">{sq.chapter_name}</span>
                      <DifficultyBadge difficulty={sq.difficulty} />
                    </div>
                    <p className="t-body-2" style={{ marginTop: 10, marginBottom: 8, color: 'var(--text)' }}>
                      {sq.question_text}
                    </p>
                    <Link to={`/questions/${sq.question_id}`} className="link-pill" style={{ fontSize: 12 }}>
                      #{sq.question_id} · 풀어보기 ›
                    </Link>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
