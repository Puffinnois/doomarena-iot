from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import yaml
from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory

from common.schemas import ExperimentConfig, TelemetryMessage, TraceRecord
from common.llm_client import create_llm_client
from agent.tools import ToolRegistry
from agent.agent import HvacAgent
from common.env import InProcessTransport, HvacEnv
from common.mqtt_transport import MqttTransport

# Attack instances & SuccessFilters
from attacks.a1_compromised import CompromisedSensorAttack, A1SuccessFilter
from attacks.a2_injection import PromptInjectionAttack, A2SuccessFilter
from attacks.a3_dos import DoSAttack, A3SuccessFilter
from attacks.a4_coordinated import CoordinatedAttack, A4SuccessFilter

app = Flask(__name__)

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

ATTACKS = {
    "none": (None, None),
    "A1": (CompromisedSensorAttack(), A1SuccessFilter()),
    "A2": (PromptInjectionAttack(), A2SuccessFilter()),
    "A3": (DoSAttack(), A3SuccessFilter()),
    "A4": (CoordinatedAttack(), A4SuccessFilter()),
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DoomArena-IoT Demo Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0a0a0f;
            --bg-surface: rgba(20, 20, 30, 0.6);
            --bg-surface-hover: rgba(30, 30, 45, 0.8);
            --border-color: rgba(255, 255, 255, 0.08);
            --border-color-active: rgba(147, 51, 234, 0.5);
            
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
            
            --accent: #a855f7;
            --accent-hover: #c084fc;
            
            --status-safe: #10b981;
            --status-blocked: #ef4444;
            --status-breached: #f59e0b;
            --status-unknown: #3b82f6;

            --font-sans: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-sans);
            line-height: 1.5;
            padding: 1.5rem;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }

        /* Header */
        .app-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        .logo-area {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-icon {
            font-size: 1.75rem;
        }

        .logo-area h1 {
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.025em;
        }

        .logo-area h1 span {
            color: var(--accent);
        }

        .status-badge {
            background: var(--bg-surface);
            border: 1px solid var(--border-color);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            font-weight: 600;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--status-unknown);
            border-radius: 50%;
            display: inline-block;
        }

        .status-badge.online .pulse-dot {
            background-color: var(--status-safe);
            box-shadow: 0 0 8px var(--status-safe);
            animation: pulse 2s infinite;
        }

        .status-badge.offline .pulse-dot {
            background-color: var(--status-breached);
            box-shadow: 0 0 8px var(--status-breached);
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.5; }
            50% { transform: scale(1.05); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.5; }
        }

        /* Grid Layout */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 420px 1fr;
            gap: 1.5rem;
            flex: 1;
        }

        /* Card panels */
        .card {
            background: var(--bg-surface);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
        }

        .panel h2 {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1.25rem;
            border-left: 3px solid var(--accent);
            padding-left: 0.5rem;
        }

        .control-group {
            margin-bottom: 1.5rem;
        }

        .control-group h3 {
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 0.75rem;
            font-weight: 600;
        }

        /* Radio Cards (Form Buttons styled as Cards) */
        .radio-cards {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .radio-cards.row {
            flex-direction: row;
        }

        .radio-cards.row form {
            flex: 1;
            display: flex;
        }

        .radio-card {
            width: 100%;
            text-align: left;
            font-family: inherit;
            color: inherit;
            cursor: pointer;
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            background: rgba(255, 255, 255, 0.02);
            transition: all 0.2s ease-in-out;
            padding: 0;
        }

        .radio-card:hover {
            background: var(--bg-surface-hover);
            border-color: rgba(255, 255, 255, 0.15);
        }

        .radio-card.active {
            border-color: var(--accent);
            background: rgba(168, 85, 247, 0.08);
            box-shadow: 0 0 12px rgba(168, 85, 247, 0.1);
        }

        .card-content {
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
        }

        .radio-cards.row .card-content {
            flex-direction: column;
            align-items: center;
            text-align: center;
            padding: 1rem 0.5rem;
            gap: 0.5rem;
        }

        .card-content .icon {
            font-size: 1.25rem;
        }

        .card-content .info {
            display: flex;
            flex-direction: column;
            gap: 0.125rem;
        }

        .card-content .title {
            font-size: 0.925rem;
            font-weight: 600;
        }

        .card-content .desc {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        /* Buttons */
        .btn {
            font-family: var(--font-sans);
            font-size: 0.95rem;
            font-weight: 600;
            padding: 0.75rem 1.5rem;
            border-radius: 0.75rem;
            border: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            transition: all 0.2s ease-in-out;
        }

        .btn-primary {
            background: var(--accent);
            color: white;
            box-shadow: 0 4px 14px rgba(168, 85, 247, 0.3);
            margin-top: 1rem;
            width: 100%;
        }

        .btn-primary:hover {
            background: var(--accent-hover);
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(168, 85, 247, 0.4);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        .btn-small {
            padding: 0.375rem 0.75rem;
            font-size: 0.8rem;
            border-radius: 0.5rem;
        }

        /* Right Side Panels */
        .traces-section {
            display: grid;
            grid-template-rows: 320px 1fr;
            gap: 1.5rem;
        }

        .traces-panel .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }

        .traces-panel h2 {
            margin-bottom: 0;
        }

        .trace-list {
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            padding-right: 0.25rem;
        }

        .empty-state {
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.875rem;
            padding: 2.5rem 0;
        }

        /* Trace List Items */
        .trace-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            text-decoration: none;
            color: inherit;
            transition: all 0.2s ease-in-out;
        }

        .trace-item:hover {
            background: var(--bg-surface-hover);
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateX(2px);
        }

        .trace-item.selected {
            border-color: var(--accent);
            background: rgba(168, 85, 247, 0.05);
        }

        .trace-item-meta {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .trace-marker {
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }

        .trace-marker.safe { background-color: var(--status-safe); box-shadow: 0 0 6px var(--status-safe); }
        .trace-marker.blocked { background-color: var(--status-blocked); box-shadow: 0 0 6px var(--status-blocked); }
        .trace-marker.breached { background-color: var(--status-breached); box-shadow: 0 0 6px var(--status-breached); }

        .trace-title {
            font-size: 0.925rem;
            font-weight: 600;
        }

        .trace-desc {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 0.125rem;
        }

        .trace-badge-group {
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }

        .badge {
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.125rem 0.5rem;
            border-radius: 0.375rem;
            text-transform: uppercase;
        }

        .badge-defense {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
        }

        .badge-attack {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: #f87171;
        }

        .badge-attack.none {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #34d399;
        }

        .trace-time {
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        /* Details Panel */
        .details-panel {
            overflow-y: auto;
            position: relative;
        }

        .empty-details {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            gap: 0.75rem;
            color: var(--text-secondary);
            text-align: center;
            padding: 3rem 0;
        }

        .empty-details span {
            font-size: 2.25rem;
        }

        .empty-details p {
            max-width: 280px;
            font-size: 0.875rem;
        }

        .details-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.75rem;
            margin-bottom: 1rem;
        }

        .details-header h2 {
            font-size: 1.25rem;
            font-weight: 600;
            border: none;
            padding: 0;
        }

        .verdict-pill {
            font-size: 0.8rem;
            font-weight: 700;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            color: white;
        }

        .verdict-pill.safe { background-color: var(--status-safe); }
        .verdict-pill.blocked { background-color: var(--status-blocked); }
        .verdict-pill.breached { background-color: var(--status-breached); }

        .metadata-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin-bottom: 1.25rem;
        }

        .metadatum {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .metadatum .label {
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
        }

        .metadatum .val {
            font-size: 0.875rem;
            font-weight: 600;
        }

        .details-section {
            margin-bottom: 1.25rem;
        }

        .details-section h3 {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
            font-weight: 600;
        }

        .telemetry-block, .verdict-block, .actions-block {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            padding: 0.75rem 1rem;
            font-size: 0.875rem;
        }

        .telemetry-row {
            display: flex;
            justify-content: space-between;
            padding: 0.25rem 0;
        }

        .telemetry-row:not(:last-child) {
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }

        .telemetry-label {
            color: var(--text-secondary);
        }

        .telemetry-val {
            font-weight: 600;
        }

        pre {
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            padding: 1rem;
            overflow-x: auto;
            font-family: Courier, monospace;
            font-size: 0.8rem;
            max-height: 250px;
        }

        code {
            color: #a7f3d0;
            white-space: pre-wrap;
        }
    </style>
</head>
<body>
    <header class="app-header">
        <div class="logo-area">
            <span class="logo-icon">🔒</span>
            <h1>DoomArena<span>-IoT</span></h1>
        </div>
        <div class="status-badge {% if is_live_mqtt %}online{% else %}offline{% endif %}">
            <span class="pulse-dot"></span>
            <span class="status-text">{% if is_live_mqtt %}Live MQTT Broker{% else %}In-Process Mode{% endif %}</span>
        </div>
    </header>

    <section class="panel card asr-panel" style="margin-bottom: 1.5rem;">
        <h2>ASR Summary Charts</h2>
        {% if not asr_heatmap_url and not asr_bars_url %}
            <div class="empty-state">No charts yet. Run harness/visualize.py to generate the ASR heatmap and bar chart.</div>
        {% else %}
            <div style="display: flex; gap: 1.5rem; flex-wrap: wrap;">
                {% if asr_heatmap_url %}
                    <div style="flex: 1; min-width: 320px;">
                        <h3 style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin-bottom: 0.5rem; font-weight: 600;">ASR Heatmap</h3>
                        <img src="{{ asr_heatmap_url }}" alt="ASR Heatmap" style="width: 100%; border-radius: 0.75rem; border: 1px solid var(--border-color);">
                    </div>
                {% endif %}
                {% if asr_bars_url %}
                    <div style="flex: 1; min-width: 320px;">
                        <h3 style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin-bottom: 0.5rem; font-weight: 600;">ASR by Attack/Defense</h3>
                        <img src="{{ asr_bars_url }}" alt="ASR Bar Chart" style="width: 100%; border-radius: 0.75rem; border: 1px solid var(--border-color);">
                    </div>
                {% endif %}
            </div>
        {% endif %}
    </section>

    <main class="dashboard-grid">
        <!-- Controls Column -->
        <section class="panel card controls-panel">
            <h2>Demo Controls</h2>
            
            <div class="control-group">
                <h3>1. Select Threat Model (Attack)</h3>
                <div class="radio-cards">
                    <form action="/config" method="POST">
                        <input type="hidden" name="defense" value="{{ defense }}">
                        
                        <button type="submit" name="attack_id" value="none" class="radio-card {% if attack_id == 'none' %}active{% endif %}">
                            <div class="card-content">
                                <span class="icon">✅</span>
                                <div class="info">
                                    <span class="title">No Attack</span>
                                    <span class="desc">Simulate normal building telemetry</span>
                                </div>
                            </div>
                        </button>
                        <div style="height: 0.5rem;"></div>
                        
                        <button type="submit" name="attack_id" value="A1" class="radio-card {% if attack_id == 'A1' %}active{% endif %}">
                            <div class="card-content">
                                <span class="icon">A1</span>
                                <div class="info">
                                    <span class="title">A1: Compromised Sensor</span>
                                    <span class="desc">Send extreme value (99 °C) to broker</span>
                                </div>
                            </div>
                        </button>
                        <div style="height: 0.5rem;"></div>
                        
                        <button type="submit" name="attack_id" value="A2" class="radio-card {% if attack_id == 'A2' %}active{% endif %}">
                            <div class="card-content">
                                <span class="icon">A2</span>
                                <div class="info">
                                    <span class="title">A2: Prompt Injection</span>
                                    <span class="desc">Embed jailbreak text in description</span>
                                </div>
                            </div>
                        </button>
                        <div style="height: 0.5rem;"></div>
                        
                        <button type="submit" name="attack_id" value="A3" class="radio-card {% if attack_id == 'A3' %}active{% endif %}">
                            <div class="card-content">
                                <span class="icon">A3</span>
                                <div class="info">
                                    <span class="title">A3: Saturation (DoS)</span>
                                    <span class="desc">Flood client messages to overwhelm agent</span>
                                </div>
                            </div>
                        </button>
                        <div style="height: 0.5rem;"></div>
                        
                        <button type="submit" name="attack_id" value="A4" class="radio-card {% if attack_id == 'A4' %}active{% endif %}">
                            <div class="card-content">
                                <span class="icon">A4</span>
                                <div class="info">
                                    <span class="title">A4: Coordinated Lie</span>
                                    <span class="desc">Multiple sensors verify warm lie (27.5 °C)</span>
                                </div>
                            </div>
                        </button>
                    </form>
                </div>
            </div>

            <div class="control-group">
                <h3>2. Select Active Defense</h3>
                <div class="radio-cards row">
                    <form action="/config" method="POST" style="display: flex; gap: 0.5rem; width: 100%;">
                        <input type="hidden" name="attack_id" value="{{ attack_id }}">
                        
                        <button type="submit" name="defense" value="none" class="radio-card {% if defense == 'none' %}active{% endif %}">
                            <div class="card-content">
                                <span class="icon">🔓</span>
                                <div class="info">
                                    <span class="title">None</span>
                                    <span class="desc">Bypass filters</span>
                                </div>
                            </div>
                        </button>
                        
                        <button type="submit" name="defense" value="D1" class="radio-card {% if defense == 'D1' %}active{% endif %}">
                            <div class="card-content">
                                <span class="icon">📊</span>
                                <div class="info">
                                    <span class="title">D1 Anomaly</span>
                                    <span class="desc">Bounds/Rates</span>
                                </div>
                            </div>
                        </button>
                        
                        <button type="submit" name="defense" value="D2" class="radio-card {% if defense == 'D2' %}active{% endif %}">
                            <div class="card-content">
                                <span class="icon">🤖</span>
                                <div class="info">
                                    <span class="title">D2 Judge</span>
                                    <span class="desc">LLM Classifier</span>
                                </div>
                            </div>
                        </button>
                    </form>
                </div>
            </div>

            <form action="/trigger" method="POST">
                <button type="submit" class="btn btn-primary">
                    <span class="btn-icon">⚡</span>
                    <span class="btn-text">Trigger Simulation Tick</span>
                </button>
            </form>
        </section>

        <!-- Traces & Details Column -->
        <section class="traces-section">
            <div class="panel card traces-panel">
                <div class="panel-header">
                    <h2>Live Trace Logs</h2>
                    <form action="/clear" method="POST" style="margin: 0;">
                        <button type="submit" class="btn btn-secondary btn-small">Clear Logs</button>
                    </form>
                </div>
                <div class="trace-list">
                    {% if not traces %}
                        <div class="empty-state">No traces logged yet. Click "Trigger Simulation Tick" to begin.</div>
                    {% else %}
                        {% for t in traces %}
                            {% set marker_class = "safe" %}
                            {% if t.defense_verdict.blocked %}
                                {% set marker_class = "blocked" %}
                            {% elif t.success %}
                                {% set marker_class = "breached" %}
                            {% endif %}
                            
                            <a href="/?select={{ t.trace_id }}" class="trace-item {% if selected_trace and selected_trace.trace_id == t.trace_id %}selected{% endif %}">
                                <div class="trace-item-meta">
                                    <span class="trace-marker {{ marker_class }}"></span>
                                    <div>
                                        <div class="trace-title">Sensor Telemetry Tick ({{ t.inputs_seen.sensor_id }})</div>
                                        <div class="trace-desc">Value: {{ t.inputs_seen.value }} {{ t.inputs_seen.unit }} | Topic: telemetry/raw</div>
                                    </div>
                                </div>
                                <div class="trace-badge-group">
                                    <span class="badge badge-defense">Def: {{ t.condition }}</span>
                                    <span class="badge badge-attack {% if t.attack_id == 'none' %}none{% endif %}">Atk: {{ t.attack_id }}</span>
                                    <span class="trace-time">{{ t.formatted_time }}</span>
                                </div>
                            </a>
                        {% endfor %}
                    {% endif %}
                </div>
            </div>

            <div class="panel card details-panel">
                {% if not selected_trace %}
                    <div class="empty-details">
                        <span>🔍</span>
                        <p>Select a trace from the timeline to inspect values, tool calls, and JSON structure.</p>
                    </div>
                {% else %}
                    <div class="details-content">
                        <div class="details-header">
                            <h2>Telemetry Audit: {{ selected_trace.trace_id[:8] }}...</h2>
                            {% if selected_trace.defense_verdict.blocked %}
                                <span class="verdict-pill blocked">BLOCKED</span>
                            {% elif selected_trace.success %}
                                <span class="verdict-pill breached">BREACHED</span>
                            {% else %}
                                <span class="verdict-pill safe">SAFE</span>
                            {% endif %}
                        </div>
                        
                        <div class="metadata-grid">
                            <div class="metadatum">
                                <span class="label">Attack Scenario</span>
                                <span class="val">{{ selected_trace.attack_id|upper }}</span>
                            </div>
                            <div class="metadatum">
                                <span class="label">Defense Active</span>
                                <span class="val">{{ selected_trace.condition|upper }}</span>
                            </div>
                            <div class="metadatum">
                                <span class="label">Execution Mode</span>
                                <span class="val">{% if selected_trace.is_live_mqtt %}Live MQTT{% else %}In-Process{% endif %}</span>
                            </div>
                            <div class="metadatum">
                                <span class="label">Timestamp</span>
                                <span class="val">{{ selected_trace.formatted_datetime }}</span>
                            </div>
                        </div>

                        <div class="details-section">
                            <h3>Input Telemetry Seen</h3>
                            <div class="telemetry-block">
                                <div class="telemetry-row">
                                    <span class="telemetry-label">Room / Sensor ID</span>
                                    <span class="telemetry-val">{{ selected_trace.inputs_seen.room_id }} / {{ selected_trace.inputs_seen.sensor_id }}</span>
                                </div>
                                <div class="telemetry-row">
                                    <span class="telemetry-label">Metric</span>
                                    <span class="telemetry-val">{{ selected_trace.inputs_seen.metric }}</span>
                                </div>
                                <div class="telemetry-row">
                                    <span class="telemetry-label">Value</span>
                                    <span class="telemetry-val">{{ selected_trace.inputs_seen.value }} {{ selected_trace.inputs_seen.unit }}</span>
                                </div>
                                <div class="telemetry-row" style="flex-direction: column; align-items: flex-start; gap: 0.25rem;">
                                    <span class="telemetry-label">Text Description Context</span>
                                    <span class="telemetry-val" style="color: var(--text-primary); font-family: monospace; word-break: break-all;">{{ selected_trace.inputs_seen.description }}</span>
                                </div>
                            </div>
                        </div>

                        <div class="details-section">
                            <h3>Defense Verdict</h3>
                            <div class="verdict-block">
                                {% if selected_trace.defense_verdict.blocked %}
                                    <div style="color: #f87171; font-weight: 600;">Blocked by Defense Guardrail</div>
                                    <div style="color: var(--text-secondary); margin-top: 0.25rem;">Reason: {{ selected_trace.defense_verdict.reason }}</div>
                                {% else %}
                                    <div style="color: #34d399; font-weight: 600;">Bypassed / Ignored</div>
                                    <div style="color: var(--text-secondary); margin-top: 0.25rem;">Telemetry passed to agent without alerts.</div>
                                {% endif %}
                            </div>
                        </div>

                        <div class="details-section">
                            <h3>Agent Decisions</h3>
                            <div class="actions-block">
                                {% if not selected_trace.tool_calls %}
                                    <div style="color: var(--text-secondary);">No action taken (execution blocked or no actions decided).</div>
                                {% else %}
                                    {% for tc in selected_trace.tool_calls %}
                                        <div style="margin-bottom: 0.5rem;">
                                            <span style="color: var(--accent); font-weight: 600;">call: {{ tc.name }}</span>
                                            <pre style="margin-top: 0.25rem; font-size: 0.75rem; padding: 0.5rem; max-height: 80px;"><code>{{ tc.args_json }}</code></pre>
                                        </div>
                                    {% endfor %}
                                    <div style="border-top: 1px solid var(--border-color); padding-top: 0.5rem; margin-top: 0.5rem; display: flex; justify-content: space-between;">
                                        <span style="color: var(--text-secondary);">Thermostat Setpoints:</span>
                                        <span style="font-weight: 600; color: var(--accent);">{{ selected_trace.final_decision_json }}</span>
                                    </div>
                                {% endif %}
                            </div>
                        </div>

                        <div class="details-section">
                            <h3>Trace Record JSON</h3>
                            <pre><code>{{ selected_trace.json_str }}</code></pre>
                        </div>
                    </div>
                {% endif %}
            </div>
        </section>
    </main>
</body>
</html>
"""

import socket

def check_broker_online(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def load_config() -> dict:
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error reading config: {e}")
    return {
        "defense": "none",
        "attack_id": "none",
        "n_trials": 5,
        "seed": 42,
        "llm_backend": "mock",
        "llm_model": ""
    }

def latest_chart_urls() -> tuple[str | None, str | None]:
    heatmaps = sorted(RESULTS_DIR.glob("asr_heatmap_*.png"))
    bars = sorted(RESULTS_DIR.glob("asr_bars_*.png"))
    heatmap_url = url_for("serve_result", filename=heatmaps[-1].name) if heatmaps else None
    bars_url = url_for("serve_result", filename=bars[-1].name) if bars else None
    return heatmap_url, bars_url

def save_config(defense: str, attack_id: str) -> None:
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    current = load_config()
    current["defense"] = defense
    current["attack_id"] = attack_id
    try:
        with open(config_path, "w") as f:
            yaml.safe_dump(current, f)
    except Exception as e:
        print(f"Error writing config: {e}")

@app.route("/results/<path:filename>")
def serve_result(filename):
    return send_from_directory(RESULTS_DIR.resolve(), filename)

@app.route("/", methods=["GET"])
def index():
    config_data = load_config()
    defense = config_data.get("defense", "none")
    attack_id = config_data.get("attack_id", "none")

    host = os.getenv("MQTT_HOST", "localhost")
    try:
        port = int(os.getenv("MQTT_PORT", 1883))
    except (ValueError, TypeError):
        port = 1883
    is_live_mqtt = check_broker_online(host, port)

    traces = []
    for filepath in RESULTS_DIR.glob("trace_*.json"):
        try:
            with open(filepath) as f:
                data = json.load(f)
            trace_obj = TraceRecord.model_validate(data)

            # Convert datetime to utc and format
            dt = trace_obj.ts.astimezone(timezone.utc)
            formatted_time = dt.strftime("%H:%M:%S")
            formatted_datetime = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

            # Check if attack was successful
            is_success = False
            if trace_obj.attack_id != "none":
                _, success_filter = ATTACKS.get(trace_obj.attack_id, (None, None))
                if success_filter:
                    try:
                        is_success = success_filter(trace_obj)
                    except Exception as filter_err:
                        print(f"Error running success filter for {trace_obj.attack_id}: {filter_err}")

            final_decision_json = json.dumps(trace_obj.final_decision)

            # Dump pydantic model to dict
            trace_dict = trace_obj.model_dump()
            trace_dict["formatted_time"] = formatted_time
            trace_dict["formatted_datetime"] = formatted_datetime
            trace_dict["success"] = is_success
            trace_dict["final_decision_json"] = final_decision_json
            trace_dict["is_live_mqtt"] = (trace_obj.notes == "mqtt")
            trace_dict["json_str"] = json.dumps(data, indent=2)

            # Add args_json to each tool call dict
            for tc_dict, tc_obj in zip(trace_dict["tool_calls"], trace_obj.tool_calls):
                tc_dict["args_json"] = json.dumps(tc_obj.args, indent=2)

            traces.append(trace_dict)
        except Exception as e:
            print(f"Error reading trace file {filepath}: {e}")

    # Sort traces descending by timestamp
    traces.sort(key=lambda t: t["ts"], reverse=True)

    selected_trace_id = request.args.get("select")
    selected_trace = None
    if selected_trace_id:
        for t in traces:
            if t["trace_id"] == selected_trace_id:
                selected_trace = t
                break
    if not selected_trace and traces:
        selected_trace = traces[0]

    asr_heatmap_url, asr_bars_url = latest_chart_urls()

    return render_template_string(
        HTML_TEMPLATE,
        defense=defense,
        attack_id=attack_id,
        is_live_mqtt=is_live_mqtt,
        traces=traces,
        selected_trace=selected_trace,
        asr_heatmap_url=asr_heatmap_url,
        asr_bars_url=asr_bars_url,
    )

@app.route("/config", methods=["POST"])
def update_config():
    defense = request.form.get("defense", "none")
    attack_id = request.form.get("attack_id", "none")
    save_config(defense, attack_id)

    host = os.getenv("MQTT_HOST", "localhost")
    try:
        port = int(os.getenv("MQTT_PORT", 1883))
    except (ValueError, TypeError):
        port = 1883

    if check_broker_online(host, port):
        try:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
            client.connect(host, port, 60)
            client.publish("system/reset", "true")
            client.disconnect()
        except Exception as e:
            print(f"Error notifying services of config update via MQTT: {e}")

    return redirect(url_for("index"))

@app.route("/trigger", methods=["POST"])
def trigger_tick():
    config_data = load_config()
    cfg = ExperimentConfig(**config_data)

    telemetry = TelemetryMessage(
        sensor_id="temp-01",
        room_id="room-a",
        ts=datetime.now(timezone.utc),
        metric="temperature",
        value=21.4,
        unit="C",
        description="Office is occupied, normal operating conditions.",
    )

    attack_id = cfg.attack_id
    if attack_id != "none":
        attack_obj, _ = ATTACKS.get(attack_id, (None, None))
        if attack_obj:
            payload = attack_obj.get_next_attack(telemetry=telemetry)
            if isinstance(payload, TelemetryMessage):
                telemetry = payload
            elif isinstance(payload, str):
                telemetry = telemetry.model_copy(update={"description": payload})

    host = os.getenv("MQTT_HOST", "localhost")
    try:
        port = int(os.getenv("MQTT_PORT", 1883))
    except (ValueError, TypeError):
        port = 1883

    is_mqtt = check_broker_online(host, port)
    trace_record = None

    if is_mqtt:
        try:
            transport = MqttTransport(config=cfg, host=host, port=port, timeout=5.0)
            trace_record = transport.publish_tick(telemetry)
            trace_record.notes = "mqtt"
        except Exception as e:
            print(f"Failed to publish via MQTT: {e}. Falling back to in-process mode.")
            is_mqtt = False

    if not is_mqtt:
        llm = create_llm_client(
            backend=os.getenv("LLM_BACKEND", cfg.llm_backend),
            model=os.getenv("LLM_MODEL", cfg.llm_model),
            api_key=os.getenv("LLM_API_KEY"),
            seed=cfg.seed,
        )

        defense_obj = None
        if cfg.defense == "D1":
            try:
                from ingest.ingest import D1Defense
                defense_obj = D1Defense()
            except ImportError:
                print("D1Defense import failed.")
        elif cfg.defense == "D2":
            try:
                from defense.llm_judge import D2Defense
                defense_obj = D2Defense(llm=llm)
            except ImportError:
                print("D2Defense import failed.")

        tools = ToolRegistry(seed=cfg.seed)
        agent = HvacAgent(llm=llm, tools=tools)
        transport = InProcessTransport(agent=agent, config=cfg, defense=defense_obj)
        trace_record = transport.publish_tick(telemetry)
        trace_record.notes = "in-process"

    trace_id = trace_record.trace_id
    filepath = RESULTS_DIR / f"trace_{trace_id}.json"
    with open(filepath, "w") as f:
        f.write(trace_record.model_dump_json())

    return redirect(url_for("index", select=trace_id))

@app.route("/clear", methods=["POST"])
def clear_logs():
    for filepath in RESULTS_DIR.glob("trace_*.json"):
        try:
            filepath.unlink()
        except Exception as e:
            print(f"Error removing trace file {filepath}: {e}")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
