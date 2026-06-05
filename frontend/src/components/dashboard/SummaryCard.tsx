import type { ReactNode } from 'react';

interface Props {
  label: ReactNode;
  value: ReactNode;
  valueColor?: string;
  detail?: string;
  style?: React.CSSProperties;
}

export default function SummaryCard({ label, value, valueColor, detail, style }: Props) {
  return (
    <div className="stat-card" style={style}>
      <div className="l">{label}</div>
      <div className="v" style={valueColor ? { color: valueColor } : undefined}>
        {value}
      </div>
      {detail && <div className="d">{detail}</div>}
    </div>
  );
}
