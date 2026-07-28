"""python -m dnsprobe 入口。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dnsprobe.config import load_config
from dnsprobe.pipeline import run


_DEFAULT_CONFIG = "config.yml"
_DEFAULT_DOMAINS = "domains.yml"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="dnsprobe")
    p.add_argument(
        "--config",
        default=_DEFAULT_CONFIG,
        help="配置文件路径（默认 config.yml）",
    )
    p.add_argument(
        "--domains",
        default=None,
        help="域名文件路径（默认与 config 同目录下的 domains.yml）",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # 让 plugins.<stem> 可被 import
    cwd = Path.cwd()
    if str(cwd) not in sys.path:
        sys.path.insert(0, str(cwd))

    try:
        domains_path = Path(args.domains) if args.domains else None
        config = load_config(Path(args.config), domains_path=domains_path)
    except FileNotFoundError as e:
        print(f"[×] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[×] 配置解析失败: {e}", file=sys.stderr)
        return 1

    plugins_dir = cwd / "plugins"
    if not plugins_dir.exists():
        plugins_dir = None

    try:
        return run(config, plugins_dir=plugins_dir)
    except Exception as e:
        print(f"[×] pipeline crashed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())