import { useNavigate } from 'react-router-dom';
import DifficultyBadge from '../ui/DifficultyBadge';

interface Props {
  rank: number;
  question_id: string;
  question_text: string;
  chapter_name: string;
  difficulty_label?: string | null;
  p_correct?: number | null;
  in_zpd: boolean;
  reason?: string;
}

export default function RecommendCard({ rank, question_id, question_text, chapter_name, difficulty_label, p_correct, in_zpd, reason }: Props) {
  const navigate = useNavigate();

  return (
    <div className="card" style={{ borderColor: in_zpd ? 'var(--accent)' : 'var(--border-soft)' }}>
      <div className="row" style={{ alignItems: 'flex-start', gap: 20 }}>
        <div className="rank-num">#{rank}</div>
        <div style={{ flex: 1 }}>
          <div className="row gap-6" style={{ flexWrap: 'wrap' }}>
            <span className="tag is-light">{chapter_name}</span>
            {difficulty_label && <DifficultyBadge difficulty={difficulty_label} />}
            {in_zpd && (
              <span className="tag is-ai">
                <span style={{ marginRight: 4 }}>✦</span>ZPD
              </span>
            )}
            {reason && <span className="tag is-light">{reason}</span>}
          </div>
          <p className="t-body" style={{ fontSize: 15, marginTop: 10, marginBottom: 12 }}>
            {question_text}
          </p>
          {p_correct != null && (
            <div className="row gap-12" style={{ alignItems: 'center' }}>
              <span className="t-caption-b" style={{ minWidth: 110 }}>
                P(correct):{' '}
                <span style={{ color: 'var(--accent)', fontFeatureSettings: '"tnum"' }}>
                  {p_correct.toFixed(2)}
                </span>
              </span>
              <div className="bar-track" style={{ flex: 1, maxWidth: 240 }}>
                <div className="bar-fill is-accent" style={{ width: `${p_correct * 100}%` }} />
              </div>
            </div>
          )}
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => navigate(`/questions/${question_id}`)}>
          풀기 ›
        </button>
      </div>
    </div>
  );
}
