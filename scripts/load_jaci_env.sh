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
#   export STACK_ROOT=/path/to/spack-stack
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

if [[ -z "${STACK_ROOT:-}" ]]; then
  echo "ERRO: STACK_ROOT is not set."
  echo "Set it to the root of the spack-stack checkout/environment, for example:"
  echo "  export STACK_ROOT=/path/to/spack-stack"
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
  return 1 2>/dev/null || exit 1
fi

if [[ ! -d "${STACK_ROOT}" ]]; then
  echo "ERRO: STACK_ROOT does not exist or is not a directory: ${STACK_ROOT}"
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
  return 1 2>/dev/null || exit 1
fi

export STACK_ROOT
export STACK_ENV_NAME="${STACK_ENV_NAME:-jaci-mpas-jedi-gcc12-craympich}"
export STACK_MODULE_ROOT="${STACK_MODULE_ROOT:-${STACK_ROOT}/envs/${STACK_ENV_NAME}/modules}"
export STACK_SITE_SETUP="${STACK_SITE_SETUP:-configs/sites/tier2/jaci/setup.sh}"
export STACK_ENV_MODULE="${STACK_ENV_MODULE:-cray-mpich/8.1.31/none/none/jedi-mpas-env/1.0.0}"

# If already loaded, do not reload. Reloading the full stack on top of itself can
# trigger module conflicts such as gcc-native/12.3 versus Spack gcc/12.3.0/*
# package modules and can leave cc/ftn with broken MPI pkg-config metadata.
case ":${LOADEDMODULES:-}:" in
  *":${STACK_ENV_MODULE}:"*)
    if [[ "${__JACI_ENV_FORCE}" != "true" ]]; then
      echo "JACI MPAS-JEDI environment already loaded; not reloading."
      echo "STACK_ENV_MODULE=${STACK_ENV_MODULE}"
      echo "PWD=$(pwd)"
      unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
      return 0 2>/dev/null || exit 0
    fi
    ;;
esac

# Clean environment. Use plain module purge rather than module --force purge,
# because the latter is not portable across all module implementations.
if ! module purge; then
  echo "ERRO: module purge failed. Start a fresh shell and try again."
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
  return 1 2>/dev/null || exit 1
fi

if ! cd "${STACK_ROOT}"; then
  echo "ERRO: cannot cd to STACK_ROOT=${STACK_ROOT}"
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
  return 1 2>/dev/null || exit 1
fi

if ! source "${STACK_SITE_SETUP}"; then
  echo "ERRO: failed to source ${STACK_SITE_SETUP}"
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
  return 1 2>/dev/null || exit 1
fi

if ! module use "${STACK_MODULE_ROOT}"; then
  echo "ERRO: failed to add module path ${STACK_MODULE_ROOT}"
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
  return 1 2>/dev/null || exit 1
fi

if ! module load "${STACK_ENV_MODULE}"; then
  echo "ERRO: failed to load ${STACK_ENV_MODULE}"
  echo "The current module state may be inconsistent. Start a fresh shell before retrying."
  cd "${__JACI_ENV_OLDPWD}" 2>/dev/null || true
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
  return 1 2>/dev/null || exit 1
fi

# Build/runtime compiler variables expected on JACI with CrayPE.
export CC="${CC:-/opt/cray/pe/craype/2.7.33/bin/cc}"
export CXX="${CXX:-/opt/cray/pe/craype/2.7.33/bin/CC}"
export FC="${FC:-/opt/cray/pe/craype/2.7.33/bin/ftn}"
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
  unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE
  return 1 2>/dev/null || exit 1
}

unset __JACI_ENV_OLDPWD __JACI_ENV_FORCE

echo "Loaded JACI MPAS-JEDI environment"
echo "STACK_ROOT=${STACK_ROOT}"
echo "STACK_ENV_NAME=${STACK_ENV_NAME}"
echo "STACK_ENV_MODULE=${STACK_ENV_MODULE}"
echo "PE_ENV=${PE_ENV:-}"
echo "GNU_VERSION=${GNU_VERSION:-}"
echo "CC=${CC}"
echo "FC=${FC}"
echo "PWD=$(pwd)"
