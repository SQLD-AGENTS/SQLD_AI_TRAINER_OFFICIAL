interface AvatarProps {
  username: string;
  size?: number;
  fontSize?: number;
  imageUrl?: string | null;
}

export default function Avatar({ username, size = 36, fontSize = 15, imageUrl }: AvatarProps) {
  const initial = username.trim().charAt(0).toUpperCase() || '?';

  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt={username}
        style={{
          width: size,
          height: size,
          borderRadius: '50%',
          objectFit: 'cover',
          flexShrink: 0,
        }}
      />
    );
  }

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
