interface Choice {
  number: number;
  text: string;
}

type Mode = 'selecting' | 'result';

interface Props {
  choices: Choice[];
  selected: number | null;
  correct?: number;
  mode: Mode;
  onSelect?: (n: number) => void;
}

export default function ChoiceList({ choices, selected, correct, mode, onSelect }: Props) {
  return (
    <div className="stack" style={{ ['--gap' as string]: '8px' }}>
      {choices.map((c) => {
        let cls = 'choice';
        if (mode === 'selecting') {
          if (selected === c.number) cls += ' is-selected';
        } else {
          if (c.number === correct) cls += ' is-correct';
          else if (c.number === selected && selected !== correct) cls += ' is-wrong';
        }

        return (
          <div
            key={c.number}
            className={cls}
            onClick={() => mode === 'selecting' && onSelect?.(c.number)}
          >
            <div className="marker">
              {mode === 'result' && c.number === correct
                ? '✓'
                : mode === 'result' && c.number === selected && selected !== correct
                  ? '✗'
                  : c.number}
            </div>
            <div className="body">
              <div>{c.text}</div>
              {mode === 'result' && c.number === selected && selected !== correct && (
                <div className="t-caption" style={{ marginTop: 4, color: 'var(--danger)' }}>
                  당신의 선택
                </div>
              )}
              {mode === 'result' && c.number === correct && (
                <div className="t-caption" style={{ marginTop: 4, color: 'var(--success)' }}>
                  정답
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
