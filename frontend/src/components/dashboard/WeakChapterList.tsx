import { Link } from 'react-router-dom';

interface ChapterStat {
  chapter_name: string;
  accuracy: number;
  attempts: number;
}

export default function WeakChapterList({ chapters }: { chapters: ChapterStat[] }) {
  const weak = [...chapters]
    .filter((c) => c.accuracy < 0.5)
    .sort((a, b) => a.accuracy - b.accuracy);

  return (
    <div className="card">
      <h3 className="t-h3">취약 챕터</h3>
      <p className="t-caption" style={{ marginTop: 4 }}>정답률 낮은 순 · 우선 학습 추천</p>
      <div style={{ marginTop: 16 }}>
        {weak.length === 0 ? (
          <p className="t-body-2" style={{ color: 'var(--success)' }}>모든 챕터 50% 이상 달성!</p>
        ) : (
          weak.map((c) => (
            <div key={c.chapter_name} className="bar-row">
              <div>
                <div className="t-body" style={{ fontSize: 14, fontWeight: 500 }}>{c.chapter_name}</div>
                <div className="t-caption">시도 {c.attempts}회</div>
              </div>
              <div className="bar-track" style={{ width: 160 }}>
                <div className="bar-fill is-danger" style={{ width: `${Math.round(c.accuracy * 100)}%` }} />
              </div>
              <div className="t-body" style={{
                fontSize: 14, fontWeight: 600, textAlign: 'right',
                color: 'var(--danger)', fontFeatureSettings: '"tnum"',
              }}>
                {Math.round(c.accuracy * 100)}%
              </div>
            </div>
          ))
        )}
      </div>
      <Link to="/questions" className="link-pill" style={{ marginTop: 12, display: 'inline-block' }}>
        해당 챕터 문제 풀기 ›
      </Link>
    </div>
  );
}
