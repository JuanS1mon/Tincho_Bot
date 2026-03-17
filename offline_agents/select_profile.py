from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


MODE_BY_PROFILE = {
    "conservative": "tryhard",
    "aggressive": "chill",
}

MODE_PRESETS = {
    "tryhard": {
        "leverage": 20,
        "stop_loss": 0.04,
        "take_profit": 0.00,
        "max_capital_per_trade": 0.50,
        "risk_per_trade": 0.03,
    },
    "chill": {
        "leverage": 10,
        "stop_loss": 0.03,
        "take_profit": 0.00,
        "max_capital_per_trade": 0.35,
        "risk_per_trade": 0.02,
    },
    "putita": {
        "leverage": 5,
        "stop_loss": 0.015,
        "take_profit": 0.00,
        "max_capital_per_trade": 0.15,
        "risk_per_trade": 0.005,
    },
}


def _load_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_profiles(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    layer2 = report.get("layer2_agentic", {}) or {}
    profiles = layer2.get("profiles", {}) or {}

    conservative = (profiles.get("conservative", {}) or {}).get("adjustments", {})
    aggressive = (profiles.get("aggressive", {}) or {}).get("adjustments", {})

    return {
        "conservative": conservative,
        "aggressive": aggressive,
    }


def _choose_profile(default_profile: str) -> str:
    print("\nSelect recommendation profile:")
    print("1) conservative (capital preservation)")
    print("2) aggressive (fast gain, higher risk)")
    print(f"Enter 1 or 2 [default={default_profile}]: ", end="")
    choice = input().strip()

    if choice == "1":
        return "conservative"
    if choice == "2":
        return "aggressive"
    return default_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select profile from two-layer report")
    parser.add_argument(
        "--report",
        type=str,
        default="reports/tincho_two_layer_report.json",
        help="Path to two-layer report JSON",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="conservative",
        choices=["conservative", "aggressive"],
        help="Profile to export",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt profile selection in terminal",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="reports/tincho_selected_profile.json",
        help="Output path for selected profile",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path = Path(args.report)
    out_path = Path(args.out)

    report = _load_report(report_path)
    profiles = _extract_profiles(report)

    if args.interactive:
        # Requested mapping: interactive mode exports PUTITA preset.
        selected = "interactive"
        tincho1_mode = "putita"
        selected_adjustments = MODE_PRESETS[tincho1_mode]
    else:
        selected = args.profile
        tincho1_mode = MODE_BY_PROFILE[selected]
        # Prioritize explicit Tincho1 mode preset so downstream is deterministic.
        selected_adjustments = MODE_PRESETS[tincho1_mode]

    # Keep report profile available for traceability.
    selected_report_profile = {
        k: v for k, v in (profiles.get(selected, {}) or {}).items() if v is not None
    } if selected in profiles else {}

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report": str(report_path).replace('\\', '/'),
        "selected_profile": selected,
        "tincho1_mode": tincho1_mode,
        "adjustments": selected_adjustments,
        "report_profile_adjustments": selected_report_profile,
        "layer2_status": (report.get("layer2_agentic", {}) or {}).get("status", "unknown"),
        "summary": (report.get("layer2_agentic", {}) or {}).get("summary", ""),
        "why": (report.get("layer2_agentic", {}) or {}).get("why", []),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    print(f"[ok] selected profile: {selected}")
    print(f"[ok] tincho1 mode: {tincho1_mode}")
    print(f"[ok] adjustments: {selected_adjustments}")
    print(f"[ok] output: {out_path}")


if __name__ == "__main__":
    main()
