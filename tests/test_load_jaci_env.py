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


def _run_loader(
    tmp_path: Path, *, already_loaded: bool, identity: str = "none"
) -> subprocess.CompletedProcess[str]:
    stack_root = _fake_stack(tmp_path)
    module_root = (
        stack_root
        / "envs"
        / "jaci-mpas-jedi-gcc12-craympich"
        / "modules"
    )
    loaded = DEFAULT_STACK_ENV_MODULE if already_loaded else ""

    if identity == "match":
        active_root = str(stack_root.resolve())
        active_module_root = str(module_root.resolve())
        active_module = DEFAULT_STACK_ENV_MODULE
    elif identity == "stale":
        active_root = str(tmp_path / "old-stack")
        active_module_root = str(tmp_path / "old-stack/modules")
        active_module = DEFAULT_STACK_ENV_MODULE
    else:
        active_root = ""
        active_module_root = ""
        active_module = ""

    script = f"""
set -u

MODULE_PURGE_COUNT=0
MODULE_LOAD_COUNT=0

module() {{
  case "$1" in
    purge)
      MODULE_PURGE_COUNT=$((MODULE_PURGE_COUNT + 1))
      unset PYTHONPATH || true
      return 0
      ;;
    use)
      return 0
      ;;
    load)
      MODULE_LOAD_COUNT=$((MODULE_LOAD_COUNT + 1))
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
export MONAN_JEDI_ACTIVE_STACK_ROOT={active_root!r}
export MONAN_JEDI_ACTIVE_STACK_MODULE_ROOT={active_module_root!r}
export MONAN_JEDI_ACTIVE_STACK_ENV_MODULE={active_module!r}
export PYTHONPATH="/preexisting/pythonpath"
unset CONDA_PREFIX
unset PYTHONHOME
unset PYTHONNOUSERSITE

source {LOADER!s}

printf 'RESULT_PYTHONPATH=%s\n' "${{PYTHONPATH-__UNSET__}}"
printf 'RESULT_PYTHONNOUSERSITE=%s\n' "${{PYTHONNOUSERSITE-__UNSET__}}"
printf 'MODULE_PURGE_COUNT=%s\n' "$MODULE_PURGE_COUNT"
printf 'MODULE_LOAD_COUNT=%s\n' "$MODULE_LOAD_COUNT"
printf 'ACTIVE_STACK_ROOT=%s\n' "${{MONAN_JEDI_ACTIVE_STACK_ROOT-__UNSET__}}"
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



def test_loader_reuses_only_matching_stack_identity(tmp_path: Path) -> None:
    result = _run_loader(tmp_path, already_loaded=True, identity="match")

    assert result.returncode == 0, result.stderr or result.stdout
    assert "MODULE_PURGE_COUNT=0" in result.stdout
    assert "MODULE_LOAD_COUNT=0" in result.stdout
    assert "already loaded from selected stack; not reloading" in result.stdout


def test_loader_reloads_same_module_name_from_stale_stack(tmp_path: Path) -> None:
    result = _run_loader(tmp_path, already_loaded=True, identity="stale")

    assert result.returncode == 0, result.stderr or result.stdout
    assert "stale or unverified" in result.stdout
    assert "MODULE_PURGE_COUNT=1" in result.stdout
    assert "MODULE_LOAD_COUNT=1" in result.stdout
    assert f"ACTIVE_STACK_ROOT={(tmp_path / 'spack-stack').resolve()}" in result.stdout
