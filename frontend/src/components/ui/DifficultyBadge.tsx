type Difficulty = 'Easy' | 'Medium' | 'Hard';

const kindMap: Record<Difficulty, string> = {
  Easy: 'easy',
  Medium: 'medium',
  Hard: 'hard',
};

export default function DifficultyBadge({ difficulty }: { difficulty: string }) {
  const kind = kindMap[difficulty as Difficulty] ?? 'medium';
  return <span className={`badge is-${kind}`}>{difficulty}</span>;
}
