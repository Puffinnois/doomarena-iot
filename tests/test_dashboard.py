from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import yaml

from dashboard.dashboard import app, RESULTS_DIR


@pytest.fixture
def temp_config_and_results(tmp_path, monkeypatch):
    # Setup temporary config
    config_file = tmp_path / "config.yaml"
    initial_config = {
        "defense": "none",
        "attack_id": "none",
        "n_trials": 5,
        "seed": 42,
        "llm_backend": "mock",
        "llm_model": ""
    }
    with open(config_file, "w") as f:
        yaml.safe_dump(initial_config, f)
        
    # Setup temporary results dir
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    
    # Apply patches via monkeypatch to redirect config and results writes
    monkeypatch.setenv("CONFIG_PATH", str(config_file))
    monkeypatch.setattr("dashboard.dashboard.RESULTS_DIR", results_dir)
    
    yield config_file, results_dir


def test_index_route_empty(temp_config_and_results):
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode()
    assert "DoomArena-IoT Demo Dashboard" in html
    assert "No traces logged yet" in html


def test_update_config_route(temp_config_and_results):
    config_file, _ = temp_config_and_results
    client = app.test_client()
    
    # Mock broker online check to False to prevent sending actual MQTT calls
    with patch("dashboard.dashboard.check_broker_online", return_value=False):
        response = client.post("/config", data={"defense": "D1", "attack_id": "A1"})
        
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    
    # Verify updated configuration
    with open(config_file) as f:
        cfg = yaml.safe_load(f)
    assert cfg["defense"] == "D1"
    assert cfg["attack_id"] == "A1"


def test_trigger_tick_route(temp_config_and_results):
    config_file, results_dir = temp_config_and_results
    client = app.test_client()
    
    with patch("dashboard.dashboard.check_broker_online", return_value=False):
        response = client.post("/trigger")
        
    assert response.status_code == 302
    
    # Verify trace file was created in the mock directory
    trace_files = list(results_dir.glob("trace_*.json"))
    assert len(trace_files) == 1
    
    # Verify the JSON keys exist
    with open(trace_files[0]) as f:
        trace_data = json.load(f)
    assert "trace_id" in trace_data
    assert trace_data["condition"] == "none"
    assert trace_data["attack_id"] == "none"
    assert "inputs_seen" in trace_data


def test_clear_route(temp_config_and_results):
    _, results_dir = temp_config_and_results
    
    # Create mock trace file
    fake_trace = results_dir / "trace_123.json"
    fake_trace.write_text("{}")
    
    client = app.test_client()
    response = client.post("/clear")
    assert response.status_code == 302
    
    # Verify it has been cleared
    assert not fake_trace.exists()
