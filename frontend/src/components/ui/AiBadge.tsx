import type { ReactNode } from 'react';

export default function AiBadge({ children = 'AI' }: { children?: ReactNode }) {
  return (
    <span className="ai-marker">
      <span className="glyph">✦</span>
      {children}
    </span>
  );
}
