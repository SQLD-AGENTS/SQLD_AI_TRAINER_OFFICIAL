import AiBadge from '../ui/AiBadge';

interface Props {
  probability: number;
}

function riskLevel(p: number) {
  if (p < 0.4) return { label: '안정', color: 'var(--success)', cls: 'is-success' };
  if (p < 0.7) return { label: '주의', color: 'var(--warning)', cls: 'is-warning' };
  return { label: '위험', color: 'var(--danger)', cls: 'is-danger' };
}

export default function RiskIndicator({ probability }: Props) {
  const risk = riskLevel(probability);
  const pct = Math.round(probability * 100);

  return (
    <div className="risk-card">
      <div className="label">
        <AiBadge>AI 예측</AiBadge>
        <span className="t-body-2" style={{ color: 'var(--text)' }}>오답 확률</span>
      </div>
      <div className="bar" style={{ flex: 1 }}>
        <div className="bar-track">
          <div className={`bar-fill ${risk.cls}`} style={{ width: `${pct}%` }} />
        </div>
      </div>
      <span className="pct" style={{ color: risk.color }}>
        {risk.label} {pct}%
      </span>
    </div>
  );
}
