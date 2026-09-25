#!/usr/bin/env bash
# =============================================================================
# Load JACI MPAS-JEDI environment
# =============================================================================
#
# This script must be sourced from this repository:
#
#   source scripts/load_jaci_env.sh
#
# It loads the spack-stack/JACI environment needed for:
#   - mpas_atmosphere
#   - mpas_init_atmosphere
#   - mpasjedi_error_covariance_toolbox.x
#   - mpasjedi_unbalance_ensemble.x / mpasjedi_process_perts.x when available
#   - gpmetis
#   - ncdump
#   - Cray MPICH/libfabric runtime
#
# Required before first use:
#
#   export STACK_ROOT=/path/to/validated/spack-stack
#
# Optional overrides:
#
#   export STACK_ENV_NAME=jaci-mpas-jedi-gcc12-craympich
#   export STACK_SITE_SETUP=configs/sites/tier2/jaci/setup.sh
#   export STACK_ENV_MODULE=cray-mpich/8.1.31/none/none/jedi-mpas-env/1.0.0
#   export STACK_MODULE_ROOT=${STACK_ROOT}/envs/${STACK_ENV_NAME}/modules
#
# Idempotency:
#   If the target jedi-mpas-env module is already loaded, this script returns
#   without reloading the environment. This avoids repeated source calls leaving
#   CrayPE/MPI in an inconsistent state.
#
# To force a clean reload:
#
#   JACI_FORCE_RELOAD=true source scripts/load_jaci_env.sh
#
# =============================================================================

# Do not use set -euo pipefail here, because this script is sourced and those
# options would affect the user's interactive shell.

__JACI_ENV_OLDPWD="$(pwd)"
__JACI_ENV_FORCE="${JACI_FORCE_RELOAD:-false}"
__JACI_ENV_CONDA_PREFIX="${CONDA_PREFIX:-}"
__JACI_ENV_STACK_INPUT="${STACK_ROOT:-}"

# Keep the command-line Python tools isolated from Python packages added by
# spack-stack. The compiled MPAS/JEDI programs still use the complete JACI
# runtime loaded below.
#
# Important: PYTHONPATH/PYTHONHOME must be sanitized even when Conda was not
# active when this script was sourced. Environment modules add spack-stack
# site-packages to PYTHONPATH; if they survive until a later "conda activate",
# Conda's python can import NumPy/xarray/etc. from spack-stack.
__jaci_sanitize_python_environment() {
  unset PYTHONHOME
  unset PYTHONPATH
  export PYTHONNOUSERSITE=1

  if [[ -n "${__JACI_ENV_CONDA_PREFIX}" && -x "${__JACI_ENV_CONDA_PREFIX}/bin/python" ]]; then
    export PATH="${__JACI_ENV_CONDA_PREFIX}/bin:${PATH}"
  fi

  hash -r 2>/dev/null || true
}

__jaci_verify_python_environment() {
  if [[ -z "${__JACI_ENV_CONDA_PREFIX}" ]]; then
    echo "WARNING: no active Conda environment was detected before loading JACI."
    echo "         PYTHONPATH was sanitized, but the current python command may"
    echo "         still be supplied by spack-stack until Conda is activated."
    return 0
  fi

  if [[ ! -x "${__JACI_ENV_CONDA_PREFIX}/bin/python" ]]; then
    echo "ERRO: active CONDA_PREFIX has no python executable: ${__JACI_ENV_CONDA_PREFIX}"
    return 1
  fi

  local __jaci_python
  local __jaci_numpy
  __jaci_python="$(command -v python 2>/dev/null || true)"

  if [[ "${__jaci_python}" != "${__JACI_ENV_CONDA_PREFIX}/bin/python" ]]; then
    echo "ERRO: Python isolation failed."
    echo "Expected: ${__JACI_ENV_CONDA_PREFIX}/bin/python"
    echo "Found:    ${__jaci_python:-<not found>}"
    return 1
  fi

  if ! __jaci_numpy="$("${__JACI_ENV_CONDA_PREFIX}/bin/python" -c 'import numpy; print(numpy.__file__)' 2>/dev/null)"; then
    echo "ERRO: NumPy cannot be imported by the active Conda Python."
    return 1
  fi

  case "${__jaci_numpy}" in
    "${__JACI_ENV_CONDA_PREFIX}"/*)
      ;;
    *)
      echo "ERRO: Python/NumPy environments are mixed."
      echo "Python: ${__jaci_python}"
      echo "NumPy:  ${__jaci_numpy}"
      echo "Expected NumPy below CONDA_PREFIX=${__JACI_ENV_CONDA_PREFIX}"
      return 1
      ;;
  esac
}

__jaci_normalize_path() {
  local path="$1"
  local resolved=""
  resolved="$(readlink -f "${path}" 2>/dev/null || true)"
  if [[ -n "${resolved}" ]]; then
    printf '%s\n' "${resolved}"
  else
    printf '%s\n' "${path%/}"
  fi
}

__jaci_stack_identity_matches() {
  local expected_root
  local expected_module_root
  expected_root="$(__jaci_normalize_path "${STACK_ROOT}")"
  expected_module_root="$(__jaci_normalize_path "${STACK_MODULE_ROOT}")"

  [[ -n "${MONAN_JEDI_ACTIVE_STACK_ROOT:-}" ]] || return 1
  [[ -n "${MONAN_JEDI_ACTIVE_STACK_MODULE_ROOT:-}" ]] || return 1
  [[ -n "${MONAN_JEDI_ACTIVE_STACK_ENV_MODULE:-}" ]] || return 1
  [[ "${MONAN_JEDI_ACTIVE_STACK_ROOT}" == "${expected_root}" ]] || return 1
  [[ "${MONAN_JEDI_ACTIVE_STACK_MODULE_ROOT}" == "${expected_module_root}" ]] || return 1
  [[ "${MONAN_JEDI_ACTIVE_STACK_ENV_MODULE}" == "${STACK_ENV_MODULE}" ]] || return 1
}

__jaci_mark_active_stack() {
  export MONAN_JEDI_ACTIVE_STACK_ROOT="$(__jaci_normalize_path "${STACK_ROOT}")"
  export MONAN_JEDI_ACTIVE_STACK_MODULE_ROOT="$(__jaci_normalize_path "${STACK_MODULE_ROOT}")"
  export MONAN_JEDI_ACTIVE_STACK_ENV_MODULE="${STACK_ENV_MODULE}"
}

if [[ -z "${STACK_ROOT:-}" ]]; then
  echo "ERRO: STACK_ROOT is not set."
  echo "Set it to the root of the spack-stack checkout/environment, for example:"
  echo "  export STACK_ROOT=/path/to/validated/spack-stack"
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

if [[ ! -d "${STACK_ROOT}" ]]; then
  echo "ERRO: STACK_ROOT does not exist or is not a directory: ${STACK_ROOT}"
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

export STACK_ENV_NAME="${STACK_ENV_NAME:-jaci-mpas-jedi-gcc12-craympich}"
export STACK_SITE_SETUP="${STACK_SITE_SETUP:-configs/sites/tier2/jaci/setup.sh}"
export STACK_ENV_MODULE="${STACK_ENV_MODULE:-cray-mpich/8.1.31/none/none/jedi-mpas-env/1.0.0}"

# Accept either the spack-stack checkout itself or its immediate parent. Resolve
# the actual checkout before deriving the module directory.
if [[ -f "${STACK_ROOT}/${STACK_SITE_SETUP}" ]]; then
  :
elif [[ -f "${STACK_ROOT}/spack-stack/${STACK_SITE_SETUP}" ]]; then
  export STACK_ROOT="${STACK_ROOT}/spack-stack"
else
  echo "ERRO: JACI setup file not found."
  echo "STACK_ROOT received: ${__JACI_ENV_STACK_INPUT}"
  echo "Expected file: ${STACK_SITE_SETUP}"
  echo "Set STACK_ROOT to a validated spack-stack checkout, for example:"
  echo "  export STACK_ROOT=/path/to/validated/spack-stack"
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

export STACK_ROOT

# STACK_MODULE_ROOT may have been exported by a previously selected stack. When
# its value is exactly the recorded old active module tree and STACK_ROOT has
# changed, treat it as stale state rather than as an intentional user override.
if [[ -n "${STACK_MODULE_ROOT:-}" && -n "${MONAN_JEDI_ACTIVE_STACK_ROOT:-}" && -n "${MONAN_JEDI_ACTIVE_STACK_MODULE_ROOT:-}" ]]; then
  if [[ "$(__jaci_normalize_path "${STACK_MODULE_ROOT}")" == "${MONAN_JEDI_ACTIVE_STACK_MODULE_ROOT}" ]] && \
     [[ "$(__jaci_normalize_path "${STACK_ROOT}")" != "${MONAN_JEDI_ACTIVE_STACK_ROOT}" ]]; then
    unset STACK_MODULE_ROOT
  fi
fi

if [[ -z "${STACK_MODULE_ROOT:-}" || ! -d "${STACK_MODULE_ROOT}" ]]; then
  export STACK_MODULE_ROOT="${STACK_ROOT}/envs/${STACK_ENV_NAME}/modules"
fi

# Reuse is safe only when both the module name and the recorded stack identity
# match the selected root/module tree. Two spack-stack installations may publish
# the same module name, so an unverified or stale identity forces a clean reload.
case ":${LOADEDMODULES:-}:" in
  *":${STACK_ENV_MODULE}:"*)
    if [[ "${__JACI_ENV_FORCE}" != "true" ]] && __jaci_stack_identity_matches; then
      __jaci_sanitize_python_environment
      if ! __jaci_verify_python_environment; then
        unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
        unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
        return 1 2>/dev/null || exit 1
      fi
      echo "JACI MPAS-JEDI environment already loaded from selected stack; not reloading."
      echo "STACK_ROOT=${STACK_ROOT}"
      echo "STACK_ENV_MODULE=${STACK_ENV_MODULE}"
      echo "Python command=$(command -v python 2>/dev/null || true)"
      echo "PWD=$(pwd)"
      unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
      unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
      return 0 2>/dev/null || exit 0
    fi
    echo "WARNING: matching module name is loaded but stack identity is stale or unverified; reloading selected STACK_ROOT."
    ;;
esac

# Clean environment. A matching module name alone does not prove stack identity.
unset MONAN_JEDI_ACTIVE_STACK_ROOT
unset MONAN_JEDI_ACTIVE_STACK_MODULE_ROOT
unset MONAN_JEDI_ACTIVE_STACK_ENV_MODULE

# Use plain module purge rather than module --force purge because the latter is
# not portable across all module implementations.
if ! module purge; then
  echo "ERRO: module purge failed. Start a fresh shell and try again."
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

if ! cd "${STACK_ROOT}"; then
  echo "ERRO: cannot cd to STACK_ROOT=${STACK_ROOT}"
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

if ! source "${STACK_SITE_SETUP}"; then
  echo "ERRO: failed to source ${STACK_SITE_SETUP}"
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

if ! module use "${STACK_MODULE_ROOT}"; then
  echo "ERRO: failed to add module path ${STACK_MODULE_ROOT}"
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

if ! module load "${STACK_ENV_MODULE}"; then
  echo "ERRO: failed to load ${STACK_ENV_MODULE}"
  echo "The current module state may be inconsistent. Start a fresh shell before retrying."
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

__jaci_mark_active_stack

# Always remove Python search paths injected by spack-stack. If Conda was
# active before loading the scientific runtime, also restore its Python command.
# This makes the result safe in both supported orders:
#
#   conda activate ... ; source load_jaci_env.sh
#   source load_jaci_env.sh ; conda activate ...
#
# In the second order, Python becomes the Conda interpreter only after
# activation, but it will no longer inherit spack-stack's PYTHONPATH.
__jaci_sanitize_python_environment
if ! __jaci_verify_python_environment; then
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
fi

# Build/runtime compiler variables expected on JACI with CrayPE.
export CC="${CC:-cc}"
export CXX="${CXX:-CC}"
export FC="${FC:-ftn}"
export F77="${F77:-${FC}}"
export F90="${F90:-${FC}}"

export MPICC="${MPICC:-${CC}}"
export MPICXX="${MPICXX:-${CXX}}"
export MPIFC="${MPIFC:-${FC}}"
export MPIF77="${MPIF77:-${FC}}"
export MPIF90="${MPIF90:-${FC}}"

# Cray compiler wrappers on JACI may need this when invoked outside the usual
# build system context.
export GNU_VERSION="${GNU_VERSION:-12.3}"

cd "${__JACI_ENV_OLDPWD}" || {
  echo "ERRO: could not return to ${__JACI_ENV_OLDPWD}"
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT
  unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack
  return 1 2>/dev/null || exit 1
}

unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE __JACI_ENV_CONDA_PREFIX __JACI_ENV_STACK_INPUT

unset -f __jaci_sanitize_python_environment __jaci_verify_python_environment __jaci_normalize_path __jaci_stack_identity_matches __jaci_mark_active_stack

echo "Loaded JACI MPAS-JEDI environment"
echo "STACK_ROOT=${STACK_ROOT}"
echo "STACK_ENV_NAME=${STACK_ENV_NAME}"
echo "STACK_ENV_MODULE=${STACK_ENV_MODULE}"
echo "PE_ENV=${PE_ENV:-}"
echo "GNU_VERSION=${GNU_VERSION:-}"
echo "CC=${CC}"
echo "FC=${FC}"
echo "Python command=$(command -v python 2>/dev/null || true)"
echo "PYTHONPATH=${PYTHONPATH:-<not set>}"
echo "PWD=$(pwd)"
