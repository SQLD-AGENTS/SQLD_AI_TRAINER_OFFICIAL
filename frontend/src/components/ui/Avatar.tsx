interface AvatarProps {
  username: string;
  size?: number;
  fontSize?: number;
}

export default function Avatar({ username, size = 36, fontSize = 15 }: AvatarProps) {
  const initial = username.trim().charAt(0).toUpperCase() || '?';

  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: 'var(--accent)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize,
        fontWeight: 700,
        color: '#fff',
        flexShrink: 0,
        userSelect: 'none',
      }}
    >
      {initial}
    </div>
  );
}
