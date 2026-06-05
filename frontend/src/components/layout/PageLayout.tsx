import type { ReactNode } from 'react';
import TopBar from './TopBar';

interface Props {
  children: ReactNode;
  wide?: boolean;
  narrow?: boolean;
}

export default function PageLayout({ children, wide, narrow }: Props) {
  const cls = ['page', wide && 'is-wide', narrow && 'is-narrow'].filter(Boolean).join(' ');
  return (
    <div className="screen">
      <TopBar />
      <div className={cls}>{children}</div>
    </div>
  );
}
