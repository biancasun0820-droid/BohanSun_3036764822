# -*- coding: utf-8 -*-
"""
run_all.py —— 端到端复现编排器（STEP 6B）

按依赖顺序执行全部分析脚本：01 → 02a → 02b → 02c → 02d → 03a → 03b → 04 → 05 → 06 → 07。
- 遇错即停（子进程返回非零即中止，整体以非零退出）。
- 所有路径相对本文件（仓库根）解析，可从任意工作目录运行。
- 每个脚本以 `-I` 隔离模式运行，避免把当前/数据目录加入 sys.path。

用法（仓库根目录）：
    python -I run_all.py            # 完整运行
    python -I run_all.py --dry-run  # 只列出步骤与脚本是否存在，不执行
"""

import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

STEPS = [
    "01_data_audit.py",
    "02a_clean_monthly.py",
    "02b_build_book_equity.py",
    "02c_prepare_ccm.py",
    "02d_build_formation_master.py",
    "03a_build_portfolios.py",
    "03b_build_market_factor.py",
    "04_validate_official.py",
    "05_extension_stability.py",
    "06_factor_importance.py",
    "07_investment_performance.py",
]


def main() -> int:
    dry = "--dry-run" in sys.argv
    mode = "（dry-run，不执行）" if dry else ""
    print(f"流水线共 {len(STEPS)} 步 {mode}", flush=True)

    for i, name in enumerate(STEPS, 1):
        script = SRC / name
        print(f"[{i:2d}/{len(STEPS)}] {name}", flush=True)
        if dry:
            if script.exists():
                print(f"      （存在）{script}", flush=True)
            else:
                print(f"      （缺失）{script}", flush=True)
            continue
        if not script.exists():
            print(f"  FAIL：脚本不存在 {script}，中止。", flush=True)
            return 1
        try:
            subprocess.run([sys.executable, "-I", str(script)],
                           cwd=ROOT, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  FAIL：{name} 返回码 {e.returncode}，流水线中止。", flush=True)
            return 1
        print(f"  OK", flush=True)

    print("全部步骤完成。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
