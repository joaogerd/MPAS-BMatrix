from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
LOADER = REPO_ROOT / "scripts" / "load_jaci_env.sh"
DEFAULT_STACK_ENV_MODULE = "cray-mpich/8.1.31/none/none/jedi-mpas-env/1.0.0"


def _fake_stack(tmp_path: Path) -> Path:
    stack_root = tmp_path / "spack-stack"
    setup = stack_root / "configs" / "sites" / "tier2" / "jaci" / "setup.sh"
    setup.parent.mkdir(parents=True)
    setup.write_text("# fake JACI setup for loader regression tests\n", encoding="utf-8")

    module_root = (
        stack_root
        / "envs"
        / "jaci-mpas-jedi-gcc12-craympich"
        / "modules"
    )
    module_root.mkdir(parents=True)
    return stack_root


def _run_loader(tmp_path: Path, *, already_loaded: bool) -> subprocess.CompletedProcess[str]:
    stack_root = _fake_stack(tmp_path)
    loaded = DEFAULT_STACK_ENV_MODULE if already_loaded else ""

    script = f"""
set -u

module() {{
  case "$1" in
    purge)
      unset PYTHONPATH || true
      return 0
      ;;
    use)
      return 0
      ;;
    load)
      export PYTHONPATH="/fake/spack/site-packages"
      export LOADEDMODULES="$2"
      return 0
      ;;
    *)
      return 0
      ;;
  esac
}}

export STACK_ROOT={stack_root!s}
export LOADEDMODULES={loaded!r}
export PYTHONPATH="/preexisting/pythonpath"
unset CONDA_PREFIX
unset PYTHONHOME
unset PYTHONNOUSERSITE

source {LOADER!s}

printf 'RESULT_PYTHONPATH=%s\n' "${{PYTHONPATH-__UNSET__}}"
printf 'RESULT_PYTHONNOUSERSITE=%s\n' "${{PYTHONNOUSERSITE-__UNSET__}}"
"""

    env = os.environ.copy()
    env.pop("CONDA_PREFIX", None)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_loader_removes_spack_pythonpath_after_module_load(tmp_path: Path) -> None:
    result = _run_loader(tmp_path, already_loaded=False)

    assert result.returncode == 0, result.stderr or result.stdout
    assert "RESULT_PYTHONPATH=__UNSET__" in result.stdout
    assert "RESULT_PYTHONNOUSERSITE=1" in result.stdout


def test_loader_removes_pythonpath_when_stack_is_already_loaded(tmp_path: Path) -> None:
    result = _run_loader(tmp_path, already_loaded=True)

    assert result.returncode == 0, result.stderr or result.stdout
    assert "RESULT_PYTHONPATH=__UNSET__" in result.stdout
    assert "RESULT_PYTHONNOUSERSITE=1" in result.stdout
