import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts';

interface ChapterStat {
  chapter_name: string;
  accuracy: number;
  total_attempts: number;
}

function barColor(accuracy: number) {
  if (accuracy >= 0.7) return '#10b981';
  if (accuracy >= 0.5) return '#f59e0b';
  return '#ef4444';
}

export default function AccuracyChart({ data }: { data: ChapterStat[] }) {
  const chartData = data.map((d) => ({
    name: d.chapter_name.split(' ')[0],
    fullName: d.chapter_name,
    accuracy: Math.round(d.accuracy * 100),
    attempts: d.total_attempts,
  }));

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h3 className="t-h3">챕터별 정답률</h3>
          <p className="t-caption" style={{ marginTop: 4 }}>
            기준선 50% · 70% 이상 안정 · 50~70% 주의 · 50% 미만 위험
          </p>
        </div>
        <div className="row gap-12">
          {[['#10b981', '안정'], ['#f59e0b', '주의'], ['#ef4444', '위험']].map(([c, l]) => (
            <span key={l} className="t-caption">
              <span style={{
                display: 'inline-block', width: 8, height: 8,
                background: c, borderRadius: 2, marginRight: 6,
              }} />
              {l}
            </span>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-soft)" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} />
            <Tooltip
              formatter={(v, _, p) => [`${v}% (${p.payload.attempts}회)`, p.payload.fullName]}
              contentStyle={{ fontSize: 13, borderRadius: 8, border: '1px solid var(--border-soft)' }}
            />
            <ReferenceLine y={50} stroke="var(--border)" strokeDasharray="4 4" />
            <Bar dataKey="accuracy" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={barColor(entry.accuracy / 100)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
