#!/usr/bin/env bash
# Run the original BMatrix scientific contract using an explicit NMC manifest.
set -euo pipefail
CASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${BMATRIX_CASE_CONFIG:-$CASE_DIR/jaci.yaml}"
ACTION="${1:-check}"
MANIFEST="${2:-${MPASWF_MANIFEST:-}}"
case "$ACTION" in
  check)
    exec mpas-bmatrix check-config --config "$CONFIG"
    ;;
  build)
    if [[ -z "$MANIFEST" ]]; then
      echo "Usage: bash testcase/tutorial-240km/run.sh build /absolute/path/to/mpas-forecast-manifest.tsv" >&2
      exit 2
    fi
    mpas-bmatrix check-config --config "$CONFIG"
    mpas-bmatrix check-manifest --config "$CONFIG" --manifest "$MANIFEST"
    exec mpas-bmatrix build --config "$CONFIG" --manifest "$MANIFEST" --from-stage bflow --to-stage dirac
    ;;
  dry-run)
    if [[ -z "$MANIFEST" ]]; then
      echo "Usage: bash testcase/tutorial-240km/run.sh dry-run /absolute/path/to/mpas-forecast-manifest.tsv" >&2
      exit 2
    fi
    exec mpas-bmatrix build --config "$CONFIG" --manifest "$MANIFEST" --from-stage bflow --to-stage dirac --dry-run
    ;;
  *)
    echo "Usage: bash testcase/tutorial-240km/run.sh [check|build|dry-run] [manifest.tsv]" >&2
    exit 2
    ;;
esac
