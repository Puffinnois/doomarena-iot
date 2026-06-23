from __future__ import annotations
import csv, json
from common.schemas import TraceRecord

ConditionResults = list[tuple[str, str, list[TraceRecord]]]  # (attack_id, condition, traces)


def asr(traces: list[TraceRecord], success_filter) -> float:
    if not traces:
        return 0.0
    successes = sum(1 for t in traces if success_filter(t))
    return successes / len(traces)


def export_csv(results: ConditionResults, path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["attack_id", "condition", "trial", "trace_id", "blocked", "setpoints"])
        for attack_id, condition, traces in results:
            for t in traces:
                writer.writerow([
                    attack_id, condition, t.trial, t.trace_id,
                    t.defense_verdict.blocked,
                    json.dumps(t.final_decision),
                ])


def export_asr_summary(asr_table: dict[str, dict[str, float]], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["attack_id", "condition", "asr"])
        for attack_id, conditions in asr_table.items():
            for condition, rate in conditions.items():
                writer.writerow([attack_id, condition, rate])


def export_json(results: ConditionResults, path: str) -> None:
    rows = []
    for attack_id, condition, traces in results:
        for t in traces:
            row = t.model_dump(mode="json")
            row["attack_id"] = attack_id
            row["condition"] = condition
            rows.append(row)
    with open(path, "w") as f:
        json.dump(rows, f, indent=2, default=str)
