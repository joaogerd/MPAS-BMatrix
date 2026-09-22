# Installation on JACI

This guide explains the JACI installation and environment setup in detail.
The end-to-end tutorial repeats the minimum operational commands required for a
first complete run, so a user does not need to leave that tutorial to continue.
Use this page for deeper installation context and troubleshooting.

The Python tools control the calculations. The compiled MPAS-JEDI, SABER and
BUMP programs are supplied separately by the MONAN-JEDI installation.

## 1. Start a new login shell

Do not reuse a shell in which spack-stack, MONAN-JEDI or another Conda
environment was previously loaded. A clean shell avoids retaining paths from
different Python installations.

## 2. Make Conda available

~~~bash
module load anaconda
start_conda
~~~

If the JACI Anaconda module reports that Conda was already initialized, continue
with the next step.

## 3. Create the environment

Create one environment for both tools. Python 3.11 is used because it is the
version adopted in the validated JACI environment.

~~~bash
conda create -n monan-jedi-bmatrix -c conda-forge \
  python=3.11 pip \
  pyyaml numpy=1.26 netcdf4 cftime xarray matplotlib \
  esmpy windspharm pytest ruff -y

conda activate monan-jedi-bmatrix
~~~

The environment is created only once. On later logins, use only:

~~~bash
module load anaconda
start_conda
conda activate monan-jedi-bmatrix
~~~

## 4. Choose the directories

The following paths are concrete JACI examples. The expression $USER is replaced
automatically by the login name of the person running the command.

~~~bash
export PROJECT_ROOT="/p/projetos/monan_das/$USER/projects"
export WORK_ROOT="/p/projetos/monan_das/$USER/work/MPAS-BMatrix"

mkdir -p "$PROJECT_ROOT" "$WORK_ROOT"
cd "$PROJECT_ROOT"
~~~

PROJECT_ROOT stores the program source. WORK_ROOT stores calculations, logs and
scientific products.

## 5. Obtain the two repositories

~~~bash
git clone https://github.com/joaogerd/mpaswf.git
git clone https://github.com/joaogerd/MPAS-BMatrix.git

export MPASWF_ROOT="$PROJECT_ROOT/mpaswf"
export BMATRIX_ROOT="$PROJECT_ROOT/MPAS-BMatrix"
~~~

If a repository already exists, do not clone it again. Enter its directory and
update it according to the branch or revision selected for the test.

## 6. Install the commands in the Conda environment

~~~bash
conda activate monan-jedi-bmatrix

python -m pip install --no-deps -e "$MPASWF_ROOT"
python -m pip install -e "$BMATRIX_ROOT"
~~~

The editable installation option, written as -e, means that an update made in
the repository is immediately used by the installed command. It also creates
the public commands:

~~~text
mpaswf
mpas-bmatrix
~~~

Normal users should call these commands directly. Setting PYTHONPATH or running
python -m bmatrix is not required.

## 7. Confirm the Python installation before loading spack-stack

~~~bash
command -v python
command -v mpaswf
command -v mpas-bmatrix

python -c "import sys, numpy; print(sys.version); print(sys.executable); print(numpy.__file__)"
~~~

The paths must begin with the active Conda environment, normally:

~~~text
/home2/<usuario>/.conda/envs/monan-jedi-bmatrix/
~~~

## 8. Load the scientific JACI environment

Select a validated spack-stack checkout and load the scientific programs. The
path must identify the spack-stack checkout containing the `configs` and
`envs` directories. On JACI this may be a shared group checkout or a
user-owned validated checkout:

~~~bash
export STACK_ROOT="/path/to/validated/spack-stack"
cd "$BMATRIX_ROOT"
source scripts/load_jaci_env.sh
~~~

The loading script retains the Conda Python for MPASWF and MPAS-BMatrix while
making the compiled MPAS-JEDI programs and scientific libraries available.

## 9. Confirm that the environments were not mixed

Repeat:

~~~bash
command -v python
command -v mpaswf
command -v mpas-bmatrix

python -c "import sys, numpy; print(sys.version); print(sys.executable); print(numpy.__file__)"
~~~

Expected result:

- Python version 3.11;
- Python executable inside monan-jedi-bmatrix;
- NumPy inside the same Conda environment;
- mpaswf and mpas-bmatrix inside the same Conda environment.

The test must not show a Conda Python loading NumPy from a path containing:

~~~text
spack-stack/.../py-numpy-.../lib/python3.11/site-packages
~~~

If that occurs, stop the test and start a new login shell. Do not try to repair
the active shell by repeatedly loading and unloading modules.

## 10. Final verification

~~~bash
mpaswf --help
mpas-bmatrix --help
mpas-bmatrix check-config --config "$BMATRIX_ROOT/configs/jaci-x1.10242.yaml"
~~~

After these commands succeed, continue with the
[end-to-end tutorial](end-to-end-tutorial.md).
