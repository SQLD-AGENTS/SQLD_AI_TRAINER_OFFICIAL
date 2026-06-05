"""
DKT (Deep Knowledge Tracing) — Phase 3 Module 2

LSTM 기반 순차 지식 상태 모델링.
입력: 사용자 풀이 이력 (question_id, is_correct) 시간순 시퀀스
출력: 다음 문제별 정답 확률 벡터 (297차원 sigmoid)
"""

import pathlib
from typing import Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence, pad_sequence
from torch.utils.data import DataLoader, Dataset

NUM_QUESTIONS = 297
EMBED_DIM = 128
HIDDEN_DIM = 128
NUM_EPOCHS = 30
BATCH_SIZE = 32
LEARNING_RATE = 1e-3
DROPOUT = 0.2
PATIENCE = 5


class DKTModel(nn.Module):
    def __init__(
        self,
        num_questions: int = NUM_QUESTIONS,
        embed_dim: int = EMBED_DIM,
        hidden_dim: int = HIDDEN_DIM,
        dropout: float = DROPOUT,
    ):
        super().__init__()
        # 0 = padding, 1~num_questions*2 = (question_idx*2 + response) + 1
        self.embedding = nn.Embedding(num_questions * 2 + 1, embed_dim, padding_idx=0)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_dim, num_questions)
        self.sigmoid = nn.Sigmoid()
        self.num_questions = num_questions

    def forward(
        self,
        input_seq: torch.Tensor,  # (batch, seq_len) LongTensor
        lengths: torch.Tensor,    # (batch,) actual sequence lengths
    ) -> torch.Tensor:
        """반환: (batch, seq_len, num_questions) sigmoid 확률"""
        embedded = self.embedding(input_seq)  # (batch, seq_len, embed_dim)
        embedded = self.dropout(embedded)

        lengths_cpu = lengths.cpu()
        packed = pack_padded_sequence(
            embedded, lengths_cpu, batch_first=True, enforce_sorted=False
        )
        lstm_out, _ = self.lstm(packed)
        output, _ = pad_packed_sequence(lstm_out, batch_first=True)  # (batch, seq_len, hidden)

        output = self.dropout(output)
        logits = self.fc(output)        # (batch, seq_len, num_questions)
        return self.sigmoid(logits)


class DKTDataset(Dataset):
    def __init__(self, sequences: list, question_to_idx: dict):
        """
        sequences: [{"question_ids": [...], "responses": [...]}]
        길이 < 2인 시퀀스 제외 (예측 페어 최소 1개 필요).
        """
        self.samples = []
        for seq in sequences:
            q_ids = seq["question_ids"]
            responses = seq["responses"]
            valid = [(q_ids[i], responses[i]) for i in range(len(q_ids)) if q_ids[i] in question_to_idx]
            if len(valid) < 2:
                continue
            q_indices = [question_to_idx[qid] for qid, _ in valid]
            resp = [r for _, r in valid]

            # input[t] = question_idx[t]*2 + response[t] + 1  (1-indexed, 0=pad)
            inputs = torch.tensor(
                [q_indices[i] * 2 + resp[i] + 1 for i in range(len(q_indices) - 1)],
                dtype=torch.long,
            )
            target_responses = torch.tensor(resp[1:], dtype=torch.float)
            target_q_indices = torch.tensor(q_indices[1:], dtype=torch.long)
            self.samples.append((inputs, target_responses, target_q_indices))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


def collate_fn(batch):
    """가변 길이 배치 패딩. 반환: (inputs, targets, target_q_idx, lengths)"""
    inputs_list, targets_list, q_idx_list = zip(*batch)
    lengths = torch.tensor([len(x) for x in inputs_list], dtype=torch.long)
    inputs_padded = pad_sequence(inputs_list, batch_first=True, padding_value=0)
    targets_padded = pad_sequence(targets_list, batch_first=True, padding_value=0)
    q_idx_padded = pad_sequence(q_idx_list, batch_first=True, padding_value=0)
    return inputs_padded, targets_padded, q_idx_padded, lengths


def build_sequences(logs_df: pd.DataFrame, question_ids: list) -> list:
    """user별 submitted_at 오름차순 시퀀스 딕셔너리 리스트 반환."""
    known_ids = set(question_ids)
    sequences = []
    for user_id, group in logs_df.groupby("user_id"):
        group = group.sort_values("submitted_at")
        q_ids = group["question_id"].tolist()
        responses = group["is_correct"].astype(int).tolist()
        filtered_q = [qid for qid in q_ids if qid in known_ids]
        filtered_r = [responses[i] for i, qid in enumerate(q_ids) if qid in known_ids]
        sequences.append({
            "user_id": user_id,
            "question_ids": filtered_q,
            "responses": filtered_r,
        })
    return sequences


def split_users(
    sequences: list,
    logs_df: pd.DataFrame,
    test_ratio: float = 0.2,
    seed: int = 42,
) -> Tuple[list, list]:
    """user_level 기준 stratified 80/20 분할."""
    rng = np.random.RandomState(seed)
    user_level_map = logs_df.drop_duplicates("user_id").set_index("user_id")["user_level"].to_dict()

    by_level = {}
    for seq in sequences:
        level = user_level_map.get(seq["user_id"], "unknown")
        by_level.setdefault(level, []).append(seq)

    train_seqs, test_seqs = [], []
    for level, seqs in by_level.items():
        seqs_arr = np.array(seqs, dtype=object)
        rng.shuffle(seqs_arr)
        n_test = max(1, int(len(seqs_arr) * test_ratio))
        test_seqs.extend(seqs_arr[:n_test].tolist())
        train_seqs.extend(seqs_arr[n_test:].tolist())

    return train_seqs, test_seqs


def train_epoch(
    model: DKTModel,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.BCELoss,
    device: torch.device,
) -> float:
    model.train()
    total_loss = 0.0
    total_count = 0

    for inputs, targets, q_idx, lengths in loader:
        inputs = inputs.to(device)
        targets = targets.to(device)
        q_idx = q_idx.to(device)

        optimizer.zero_grad()
        outputs = model(inputs, lengths)  # (B, T, num_questions)

        # 각 스텝 t에서 t+1 문제의 logit 추출
        target_logits = outputs.gather(
            dim=2, index=q_idx.unsqueeze(-1)
        ).squeeze(-1)  # (B, T)

        # 유효 위치 마스크 (패딩 제외)
        max_len = inputs.size(1)
        mask = torch.arange(max_len, device=device).unsqueeze(0) < lengths.to(device).unsqueeze(1)

        loss = criterion(target_logits[mask], targets[mask])
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item() * mask.sum().item()
        total_count += mask.sum().item()

    return total_loss / max(total_count, 1)


def evaluate(
    model: DKTModel,
    loader: DataLoader,
    device: torch.device,
) -> float:
    """유효 위치 전체에 대한 AUC-ROC 반환."""
    model.eval()
    all_targets = []
    all_preds = []

    with torch.no_grad():
        for inputs, targets, q_idx, lengths in loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            q_idx = q_idx.to(device)

            outputs = model(inputs, lengths)
            target_logits = outputs.gather(
                dim=2, index=q_idx.unsqueeze(-1)
            ).squeeze(-1)

            max_len = inputs.size(1)
            mask = torch.arange(max_len, device=device).unsqueeze(0) < lengths.to(device).unsqueeze(1)

            all_targets.extend(targets[mask].cpu().numpy())
            all_preds.extend(target_logits[mask].cpu().numpy())

    if len(set(all_targets)) < 2:
        return 0.5
    return roc_auc_score(all_targets, all_preds)


def train_dkt(
    train_seqs: list,
    test_seqs: list,
    question_to_idx: dict,
    device: torch.device,
    num_epochs: int = NUM_EPOCHS,
    batch_size: int = BATCH_SIZE,
    lr: float = LEARNING_RATE,
    patience: int = PATIENCE,
) -> Tuple[DKTModel, dict]:
    """Early stopping 포함 전체 학습 루프. 반환: (best_model, metrics_dict)"""
    train_dataset = DKTDataset(train_seqs, question_to_idx)
    test_dataset = DKTDataset(test_seqs, question_to_idx)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True,
        collate_fn=collate_fn, drop_last=False
    )
    test_loader = DataLoader(
        test_dataset, batch_size=batch_size, shuffle=False,
        collate_fn=collate_fn
    )

    model = DKTModel(num_questions=len(question_to_idx)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.BCELoss()

    best_val_auc = 0.0
    best_epoch = 0
    best_state = None
    patience_counter = 0
    train_losses = []
    val_aucs = []

    print(f"[DKT] 학습 시작 - train: {len(train_dataset)}개 시퀀스, test: {len(test_dataset)}개 시퀀스")
    print(f"[DKT] 디바이스: {device}, epochs: {num_epochs}, batch: {batch_size}")

    for epoch in range(1, num_epochs + 1):
        loss = train_epoch(model, train_loader, optimizer, criterion, device)
        val_auc = evaluate(model, test_loader, device)
        train_losses.append(loss)
        val_aucs.append(val_auc)

        print(f"[DKT] Epoch {epoch:02d}/{num_epochs} | loss: {loss:.4f} | val AUC: {val_auc:.4f}")

        if val_auc > best_val_auc:
            best_val_auc = val_auc
            best_epoch = epoch
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"[DKT] Early stopping at epoch {epoch} (patience={patience})")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    metrics = {
        "train_losses": train_losses,
        "val_aucs": val_aucs,
        "best_val_auc": best_val_auc,
        "best_epoch": best_epoch,
        "final_train_loss": train_losses[-1],
    }
    print(f"[DKT] 최종 Best Val AUC-ROC: {best_val_auc:.4f} (Epoch {best_epoch})")
    return model, metrics


def predict_next(
    model: DKTModel,
    user_sequence: dict,
    question_to_idx: dict,
    device: torch.device,
) -> np.ndarray:
    """단일 유저 이력으로 다음 문제별 정답 확률 반환. shape: (num_questions,)"""
    model.eval()
    q_ids = user_sequence["question_ids"]
    responses = user_sequence["responses"]

    valid = [(qid, r) for qid, r in zip(q_ids, responses) if qid in question_to_idx]
    if not valid:
        return np.full(model.num_questions, 0.5, dtype=np.float32)

    q_indices = [question_to_idx[qid] for qid, _ in valid]
    resp = [r for _, r in valid]
    tokens = [q_indices[i] * 2 + resp[i] + 1 for i in range(len(q_indices))]

    input_tensor = torch.tensor(tokens, dtype=torch.long).unsqueeze(0).to(device)
    lengths = torch.tensor([len(tokens)], dtype=torch.long)

    with torch.no_grad():
        output = model(input_tensor, lengths)  # (1, seq_len, num_questions)
    last_out = output[0, -1, :].cpu().numpy()  # (num_questions,)
    return last_out.astype(np.float32)


def save_knowledge_tracer(
    model: DKTModel,
    question_ids: list,
    metrics: dict,
    model_dir: pathlib.Path,
):
    """
    아티팩트 저장:
      models/dkt_model.pth
      models/dkt_question_ids.joblib
    """
    model_dir.mkdir(exist_ok=True)
    torch.save(model.state_dict(), model_dir / "dkt_model.pth")
    joblib.dump(question_ids, model_dir / "dkt_question_ids.joblib")
    print(f"[DKT] 아티팩트 저장 완료 → {model_dir}")


def load_knowledge_tracer(
    model_dir: pathlib.Path,
    device: torch.device = None,
) -> Tuple[DKTModel, list]:
    """state_dict + question_ids 로드. 반환: (model, question_ids)"""
    if device is None:
        device = torch.device("cpu")
    question_ids = joblib.load(model_dir / "dkt_question_ids.joblib")
    question_to_idx = {qid: i for i, qid in enumerate(question_ids)}
    model = DKTModel(num_questions=len(question_to_idx))
    model.load_state_dict(torch.load(model_dir / "dkt_model.pth", map_location=device))
    model.to(device)
    model.eval()
    return model, question_ids


def run_knowledge_tracer(
    questions_path: pathlib.Path,
    logs_path: pathlib.Path,
    model_dir: pathlib.Path,
    report_dir: pathlib.Path,
) -> dict:
    """pipeline.py 진입점. 반환: metrics dict"""
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    print(f"\n[DKT] 데이터 로드 중 (device={device})...")
    questions_df = pd.read_csv(questions_path)
    logs_df = pd.read_csv(logs_path)
    question_ids = questions_df["question_id"].tolist()
    question_to_idx = {qid: i for i, qid in enumerate(question_ids)}

    sequences = build_sequences(logs_df, question_ids)
    train_seqs, test_seqs = split_users(sequences, logs_df)
    print(f"[DKT] 유저 분할 - train: {len(train_seqs)}명, test: {len(test_seqs)}명")

    model, metrics = train_dkt(
        train_seqs, test_seqs, question_to_idx, device
    )
    save_knowledge_tracer(model, question_ids, metrics, model_dir)

    # 보고서 저장
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "dkt_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=== DKT (Deep Knowledge Tracing) 평가 보고서 ===\n\n")
        f.write(f"Best Val AUC-ROC : {metrics['best_val_auc']:.4f}\n")
        f.write(f"Best Epoch       : {metrics['best_epoch']}\n")
        f.write(f"Final Train Loss : {metrics['final_train_loss']:.4f}\n\n")
        f.write("Epoch별 Val AUC:\n")
        for i, auc in enumerate(metrics["val_aucs"], 1):
            f.write(f"  Epoch {i:02d}: {auc:.4f}\n")
    print(f"[DKT] 보고서 저장 완료 → {report_path}")

    return metrics
