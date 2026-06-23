#!/usr/bin/env python3
from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from common.schemas import ExperimentConfig, TelemetryMessage
from common.llm_client import create_llm_client
from common.env import InProcessTransport, HvacEnv
from agent.tools import ToolRegistry
from agent.agent import HvacAgent
from attacks.mqtt_gateway import MqttAttackGateway
from attacks.a1_compromised import CompromisedSensorAttack, A1SuccessFilter
from attacks.a2_injection import PromptInjectionAttack, A2SuccessFilter
from attacks.a3_dos import DoSAttack, A3SuccessFilter
from attacks.a4_coordinated import CoordinatedAttack, A4SuccessFilter
from harness.metrics import asr, export_csv, export_json, export_asr_summary

load_dotenv()

ATTACKS = {
    "A1": (CompromisedSensorAttack, A1SuccessFilter),
    "A2": (PromptInjectionAttack, A2SuccessFilter),
    "A3": (DoSAttack, A3SuccessFilter),
    "A4": (CoordinatedAttack, A4SuccessFilter),
}
CONDITIONS = ["none", "D1", "D2"]

BASE_TELEMETRY = TelemetryMessage(
    sensor_id="temp-01",
    room_id="room-a",
    ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
    metric="temperature",
    value=21.4,
    unit="C",
    description="Office is occupied, normal operating conditions.",
)


def _load_config() -> ExperimentConfig:
    raw = yaml.safe_load(Path("config.yaml").read_text())
    return ExperimentConfig(**raw)


def _build_defense(condition: str, cfg: ExperimentConfig):
    if condition == "D1":
        try:
            from ingest.ingest import D1Defense
            return D1Defense()
        except ImportError:
            print(f"  [warn] D1Defense not found, treating as 'none'")
            return None
    if condition == "D2":
        try:
            from defense.llm_judge import D2Defense
            llm = create_llm_client(
                backend=os.getenv("LLM_BACKEND", cfg.llm_backend),
                model=os.getenv("LLM_MODEL", cfg.llm_model),
                api_key=os.getenv("LLM_API_KEY"),
                seed=cfg.seed,
            )
            return D2Defense(llm=llm)
        except ImportError:
            print(f"  [warn] D2Defense not found, treating as 'none'")
            return None
    return None


def _build_gateway(attack_id: str, condition: str, cfg: ExperimentConfig):
    run_cfg = cfg.model_copy(update={"defense": condition, "attack_id": attack_id})
    llm = create_llm_client(
        backend=os.getenv("LLM_BACKEND", cfg.llm_backend),
        model=os.getenv("LLM_MODEL", cfg.llm_model),
        api_key=os.getenv("LLM_API_KEY"),
        seed=cfg.seed,
    )
    tools = ToolRegistry(seed=cfg.seed)
    agent = HvacAgent(llm=llm, tools=tools)
    defense = _build_defense(condition, cfg)
    transport = InProcessTransport(agent=agent, config=run_cfg, defense=defense)
    env = HvacEnv(transport=transport, config=run_cfg)

    attack_cls, filter_cls = ATTACKS[attack_id]
    attack, success_filter = attack_cls(), filter_cls()

    class _AC:
        def __init__(self):
            self.attack = attack
            self.filter = None
            self.success_filter = success_filter

    return MqttAttackGateway(env=env, attack_configs=[_AC()]), success_filter, defense


def run() -> None:
    cfg = _load_config()
    results = []
    asr_table: dict[str, dict[str, float]] = {a: {} for a in ATTACKS}

    for attack_id in ATTACKS:
        for condition in CONDITIONS:
            gw, sf, defense = _build_gateway(attack_id, condition, cfg)
            gw.reset()
            traces = []
            for _ in range(cfg.n_trials):
                # Each trial is an independent ASR sample, not a continuation of a
                # message flood — except for A3, where the trial loop *is* the
                # flood (burst_seq deliberately accumulates so D1's per-sensor
                # rate counter trips at the same point). Reset D1's rate state
                # between trials for every other attack so n_trials > rate_limit
                # doesn't spuriously trip D1 on trial volume alone.
                if attack_id != "A3" and hasattr(defense, "reset_counts"):
                    defense.reset_counts()
                trace = gw.step(BASE_TELEMETRY)
                traces.append(trace)
            rate = asr(traces, sf)
            asr_table[attack_id][condition] = rate
            results.append((attack_id, condition, traces))

    # Print table
    col_w = 10
    print(f"\n{'Attack':<8}" + "".join(f"{c:<{col_w}}" for c in CONDITIONS))
    print("-" * (8 + col_w * len(CONDITIONS)))
    for attack_id, conds in asr_table.items():
        print(f"{attack_id:<8}" + "".join(f"{conds[c]:.2f}{'':>{col_w-4}}" for c in CONDITIONS))

    Path("results").mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    export_csv(results, f"results/traces_{ts}.csv")
    export_json(results, f"results/traces_{ts}.json")
    export_asr_summary(asr_table, f"results/asr_summary_{ts}.csv")
    print(f"\nExported -> results/traces_{ts}.{{csv,json}}, results/asr_summary_{ts}.csv")


if __name__ == "__main__":
    run()
