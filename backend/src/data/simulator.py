import numpy as np
import pandas as pd
from datetime import datetime, timedelta

BASE_ACCURACY = {"beginner": 0.40, "intermediate": 0.65, "advanced": 0.85}
DIFFICULTY_PENALTY = {0: 0.0, 1: -0.05, 2: -0.15}
SOLVE_TIME_PARAMS = {0: (30, 10), 1: (60, 15), 2: (90, 20)}  # (mean, std) in seconds
KNOWLEDGE_GAIN = 0.02
MAX_ACCURACY = 0.95

USER_DISTRIBUTION = {
    "beginner": 0.40,
    "intermediate": 0.40,
    "advanced": 0.20,
}

NUM_USERS = 100
RANDOM_SEED = 42


def _assign_user_levels(num_users: int, rng: np.random.Generator) -> list[str]:
    levels, probs = zip(*USER_DISTRIBUTION.items())
    return list(rng.choice(list(levels), size=num_users, p=list(probs)))


def _simulate_user(user_id: str, level: str, questions_df: pd.DataFrame, rng: np.random.Generator) -> list[dict]:
    base_acc = BASE_ACCURACY[level]
    start_date = datetime(2025, 1, 1)
    rows = []
    attempt_counter: dict[str, int] = {}

    # 각 사용자는 전체 문제를 1~3회 랜덤 풀이
    num_attempts = rng.integers(1, 4)
    for attempt_round in range(num_attempts):
        shuffled = questions_df.sample(frac=1, random_state=int(rng.integers(0, 10000))).reset_index(drop=True)
        elapsed_days = attempt_round * 14  # 라운드당 2주 간격

        for _, q in shuffled.iterrows():
            qid = q["question_id"]
            difficulty = int(q["difficulty"])
            attempt_counter[qid] = attempt_counter.get(qid, 0) + 1
            cnt = attempt_counter[qid]

            # Knowledge Tracing: 반복할수록 정답률 상승
            acc = min(base_acc + DIFFICULTY_PENALTY[difficulty] + KNOWLEDGE_GAIN * (cnt - 1), MAX_ACCURACY)
            acc = max(acc, 0.05)

            is_correct = bool(rng.random() < acc)

            mean_t, std_t = SOLVE_TIME_PARAMS[difficulty]
            solve_time = max(5, int(rng.normal(mean_t, std_t)))

            question_offset = int(q.name)
            submitted_at = start_date + timedelta(days=elapsed_days) + timedelta(minutes=question_offset * 2)

            rows.append({
                "user_id": user_id,
                "question_id": qid,
                "user_level": level,
                "is_correct": is_correct,
                "solve_time_sec": solve_time,
                "submitted_at": submitted_at.strftime("%Y-%m-%dT%H:%M:%S"),
                "attempt_count": cnt,
            })

    return rows


def generate_logs(questions_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    levels = _assign_user_levels(NUM_USERS, rng)
    all_rows = []

    for i, level in enumerate(levels):
        user_id = f"user_{i+1:03d}"
        all_rows.extend(_simulate_user(user_id, level, questions_df, rng))

    return pd.DataFrame(all_rows)


if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from json_parser import parse_all
    from features import add_features

    questions = add_features(parse_all())
    logs = generate_logs(questions)
    print(f"총 로그 수: {len(logs)}")
    print(f"사용자 수: {logs['user_id'].nunique()}")
    print(f"전체 정답률: {logs['is_correct'].mean():.3f}")
    print("\n사용자 레벨별 정답률:")
    print(logs.groupby("user_level")["is_correct"].mean().round(3))
