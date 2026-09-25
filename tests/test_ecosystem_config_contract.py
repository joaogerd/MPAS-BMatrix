from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ab_helpers_do_not_reread_public_install_root_from_environment() -> None:
    for relative in (
        "src/bmatrix/ab_compare_pbs.py",
        "src/bmatrix/ab_so_diag_pbs.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert 'os.environ.get("MONAN_JEDI_INSTALL_ROOT")' not in source
        assert 'config.get("install"' in source


def test_jaci_config_binds_only_public_ecosystem_anchors() -> None:
    text = (ROOT / "configs/jaci.yaml").read_text(encoding="utf-8")

    assert "root: ${MONAN_JEDI_INSTALL_ROOT}" in text
    assert "STACK_ROOT: ${STACK_ROOT}" in text
    assert "MONAN_JEDI_SOURCE" not in text
    assert "MONAN_JEDI_BUILD_DIR" not in text


def test_tutorials_do_not_publish_project_root_as_ecosystem_api() -> None:
    for relative in (
        "docs/README.md",
        "docs/workflow.md",
        "docs/user-guide.md",
        "docs/install-jaci.md",
        "docs/mpaswf-pairs.md",
        "docs/end-to-end-tutorial.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "export PROJECT_ROOT" not in text
        assert "export REPOS_ROOT" in text


def test_legacy_mpas_templates_have_no_personal_root_defaults() -> None:
    for path in (ROOT / "templates/pbs").glob("run_mpas*.pbs"):
        text = path.read_text(encoding="utf-8")
        assert "/p/projetos/monan_das/joao.gerd" not in text
        assert "PROJECT_ROOT" not in text


def test_loader_tracks_selected_stack_identity() -> None:
    source = (ROOT / "scripts/load_jaci_env.sh").read_text(encoding="utf-8")

    assert "MONAN_JEDI_ACTIVE_STACK_ROOT" in source
    assert "MONAN_JEDI_ACTIVE_STACK_MODULE_ROOT" in source
    assert "MONAN_JEDI_ACTIVE_STACK_ENV_MODULE" in source
    assert "__jaci_stack_identity_matches" in source
    assert "stale or unverified" in source
