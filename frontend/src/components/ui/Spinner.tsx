type Size = 'sm' | 'md' | 'lg';

export default function Spinner({ size = 'md' }: { size?: Size }) {
  const cls = ['spinner', size === 'sm' && 'is-sm', size === 'lg' && 'is-lg']
    .filter(Boolean).join(' ');
  return <span className={cls} />;
}
