# app/entry_gui.py
from app.config import load_config_from_gui
from app.run_once import run_once

def main():
    cfg = load_config_from_gui()  # GUIで選んだシナリオ/期間/プラグイン
    result = run_once(cfg)
    # GUIは result を受け取って描画。CSV/PDF出力は exporter フックで済ます
