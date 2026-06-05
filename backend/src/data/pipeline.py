import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from json_parser import parse_all
from features import add_features
from simulator import generate_logs

OUTPUT_DIR = pathlib.Path(__file__).parents[2] / "outputs"


def run():
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("1/3  JSON 파싱 중...")
    questions = parse_all()
    print(f"     → 문제 수: {len(questions)}")

    print("2/3  Feature 생성 및 난이도 추정 중...")
    questions = add_features(questions)
    dist = questions["difficulty_label"].value_counts().to_dict()
    print(f"     → 난이도 분포: {dist}")

    questions_path = OUTPUT_DIR / "questions.csv"
    questions.to_csv(questions_path, index=False, encoding="utf-8-sig")
    print(f"     → 저장: {questions_path}")

    print("3/3  시뮬레이션 학습 이력 생성 중...")
    logs = generate_logs(questions)
    print(f"     → 로그 수: {len(logs)}  |  사용자 수: {logs['user_id'].nunique()}")
    acc_by_level = logs.groupby("user_level")["is_correct"].mean().round(3).to_dict()
    print(f"     → 레벨별 정답률: {acc_by_level}")

    logs_path = OUTPUT_DIR / "user_logs.csv"
    logs.to_csv(logs_path, index=False, encoding="utf-8-sig")
    print(f"     → 저장: {logs_path}")

    print("\n완료.")
    _verify(questions, logs)


def _verify(questions, logs):
    errors = []

    if questions["question_id"].duplicated().any():
        errors.append("question_id 중복 존재")

    for label in ["Easy", "Medium", "Hard"]:
        ratio = (questions["difficulty_label"] == label).mean()
        if ratio < 0.05:
            errors.append(f"difficulty '{label}' 비율이 너무 낮음: {ratio:.2%}")

    if errors:
        print("\n[검증 실패]")
        for e in errors:
            print(f"  - {e}")
    else:
        print("[검증 통과] 모든 항목 정상")


if __name__ == "__main__":
    run()
