"""
run_tests.py
============
Ejecuta la suite de tests de Tincho Bot con reporte visual.

Uso:
  python run_tests.py              # tests rápidos (sin Binance)
  python run_tests.py --all        # todos los tests (incluye conexión Binance)
  python run_tests.py --binance    # solo tests de conexión Binance
  python run_tests.py --verbose    # output detallado
"""
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTEST = ROOT / ".venv" / "Scripts" / "pytest.exe"


def run(args: list[str]) -> int:
    cmd = [str(PYTEST)] + args
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


def main() -> None:
    argv = sys.argv[1:]
    verbose = "-v" in argv or "--verbose" in argv

    print("\n" + "=" * 60)
    print("  Tincho Bot — Suite de Tests")
    print("=" * 60)

    base_args = ["-v"] if verbose else ["--tb=short", "-q"]

    if "--binance" in argv:
        print("  Modo: solo tests de conexión Binance\n")
        code = run(base_args + ["tests/test_binance_connection.py", "-v"])

    elif "--all" in argv:
        print("  Modo: todos los tests (incluye Binance live)\n")
        code = run(base_args + ["tests/"])

    else:
        # Por defecto: tests rápidos (sin conexión Binance)
        print("  Modo: tests rápidos (sin conexión Binance)\n")
        code = run(base_args + [
            "tests/test_settings.py",
            "tests/test_indicators.py",
            "tests/test_risk_tool.py",
            "tests/test_portfolio.py",
            "tests/test_trend_and_signals.py",
        ])

    print("\n" + "=" * 60)
    if code == 0:
        print("  RESULTADO: ✓ Todos los tests pasaron")
        print("  El bot está listo para correr.")
    else:
        print("  RESULTADO: ✗ Hay tests fallando")
        print("  Revisar errores antes de correr el bot.")
    print("=" * 60 + "\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
