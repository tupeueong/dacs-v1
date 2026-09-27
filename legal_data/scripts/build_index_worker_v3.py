"""Build a verified staging index and exit before Windows directory promotion.

This wrapper keeps the v2 builder logic as the single implementation while ensuring
that all Chroma handles are released when this process exits. The parent process can
then move the staging directory atomically on Windows.
"""

from __future__ import annotations

from pathlib import Path

import build_index_v2


class StagingComplete(RuntimeError):
    pass


def main() -> int:
    original_replace = Path.replace

    def stop_before_promotion(path: Path, target: Path):
        if path.name.endswith(".staging"):
            raise StagingComplete(str(path))
        return original_replace(path, target)

    Path.replace = stop_before_promotion  # type: ignore[method-assign]
    try:
        return build_index_v2.main()
    except StagingComplete as event:
        print(f"STAGING_COMPLETE={event}", flush=True)
        return 0
    finally:
        Path.replace = original_replace  # type: ignore[method-assign]


if __name__ == "__main__":
    raise SystemExit(main())
