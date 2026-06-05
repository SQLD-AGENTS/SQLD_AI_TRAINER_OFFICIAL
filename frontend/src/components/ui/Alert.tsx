type Kind = 'error' | 'success' | 'info';

interface Props {
  kind?: Kind;
  message: string;
}

export default function Alert({ kind = 'error', message }: Props) {
  return <div className={`alert is-${kind}`}>{message}</div>;
}
