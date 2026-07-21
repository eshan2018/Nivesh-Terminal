"""Tests for the architecture guardrails.

Each guardrail is proven twice: it must PASS on a clean tree and FAIL on a planted
violation. Planted violations are written into a temporary ``backend/`` tree so the
real repository tree stays clean (a fixture containing ``import yfinance`` must not
trip the real CI run). A final test asserts the committed skeleton is clean.
"""
from __future__ import annotations

import ast
from pathlib import Path

from tools.ci import architecture_map as amap
from tools.ci import (
    check,
    layer_dependencies,
    module_schema_isolation,
    vendor_isolation,
)
from tools.ci._scan import iter_source_files

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_backend(root: Path, files: dict[str, str]) -> Path:
    """Materialize a fake ``backend/`` tree under ``root`` from {relpath: source}.

    Every directory under ``backend`` is made a package (empty ``__init__.py``).
    """
    backend = root / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    for relpath, source in files.items():
        path = backend / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    directories = [backend, *(p for p in backend.rglob("*") if p.is_dir())]
    for directory in directories:
        init = directory / "__init__.py"
        if not init.exists():
            init.write_text('"""test package."""\n', encoding="utf-8")
    return backend


# ── Clean trees pass ──────────────────────────────────────────────────────────

def test_clean_tree_has_no_violations(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            "platform/types.py": "VALUE = 1\n",
            "features/returns.py": "from backend.platform import types\n",
            "analytics/one_year_return.py": (
                "from backend.platform import types\n"
                "from backend.features import returns\n"
            ),
        },
    )
    assert check.run(backend) == []


# ── Dependency-direction ──────────────────────────────────────────────────────

def test_dependency_direction_blocks_upward_import(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            # analytics (L7) may import features + model, but NOT the domain repositories.
            "analytics/engine.py": "from backend.domain.market_data import repository\n",
        },
    )
    violations = layer_dependencies.check(backend)
    assert len(violations) == 1
    assert violations[0].rule == "dependency-direction"
    assert violations[0].lineno == 1
    assert "backend.analytics" in violations[0].message


def test_dependency_direction_resolves_relative_imports(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            # `from ..domain.market_data import x` inside analytics resolves upward.
            "analytics/engine.py": "from ..domain.market_data import repository\n",
        },
    )
    violations = layer_dependencies.check(backend)
    assert len(violations) == 1
    assert violations[0].rule == "dependency-direction"


def test_dependency_direction_allows_permitted_and_kernel(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            "api/routes.py": (
                "from backend.platform import types\n"  # kernel: always allowed
                "from backend.analytics import engine\n"  # L9 -> L7: allowed
            ),
        },
    )
    assert layer_dependencies.check(backend) == []


# ── Vendor isolation ──────────────────────────────────────────────────────────

def test_vendor_name_above_l1_is_flagged(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            "ingestion/normalize.py": "import yfinance\n\nyfinance.download('AAPL')\n",
        },
    )
    violations = vendor_isolation.check(backend)
    assert violations, "expected a vendor-isolation violation"
    assert all(v.rule == "no-vendor-above-L1" for v in violations)
    assert 1 in {v.lineno for v in violations}  # the import line


def test_vendor_name_in_adapter_home_is_allowed(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            "providers/yfinance/adapter.py": "import yfinance\n\nyfinance.download('AAPL')\n",
        },
    )
    assert vendor_isolation.check(backend) == []


def test_vendor_name_in_docstring_is_not_flagged(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            # prose mentioning a vendor is fine — only *code* leakage is a violation.
            "ingestion/normalize.py": '"""Not a yfinance-specific module."""\n',
        },
    )
    assert vendor_isolation.check(backend) == []


# ── Module-schema isolation ───────────────────────────────────────────────────

def test_cross_module_domain_import_is_flagged(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            "domain/other/repo.py": "from backend.domain.market_data import tables\n",
        },
    )
    violations = module_schema_isolation.check(backend)
    assert len(violations) == 1
    assert violations[0].rule == "module-schema-isolation"


def test_domain_module_may_use_shared_model(tmp_path: Path) -> None:
    backend = _write_backend(
        tmp_path,
        {
            "domain/market_data/repo.py": "from backend.domain.model import instrument\n",
        },
    )
    assert module_schema_isolation.check(backend) == []


# ── The real repository skeleton must be clean ────────────────────────────────

def test_real_backend_skeleton_is_clean() -> None:
    backend = REPO_ROOT / "backend"
    assert backend.is_dir()
    assert check.run(backend) == []


# ── Map sanity ────────────────────────────────────────────────────────────────

def test_every_allowed_target_is_a_known_layer() -> None:
    known = set(amap.ALLOWED_IMPORTS) | {amap.KERNEL}
    for importer, targets in amap.ALLOWED_IMPORTS.items():
        for target in targets:
            assert target in known, f"{importer} allows unknown layer {target}"

# ── The composition root (ED-011) ─────────────────────────────────────────────


def test_the_composition_root_is_the_only_module_outside_the_layer_graph() -> None:
    """The layer lint skips modules belonging to no layer, so an undeclared one would
    be silently exempt from every dependency rule.

    ED-011 sanctions exactly one such module — the process entry point, which must be
    free to construct across layers. This asserts the exemption stays a decision rather
    than becoming a hiding place: a second unlayered module under `backend/` fails here.
    """
    backend = REPO_ROOT / "backend"
    # `backend` is the package root marker and `backend.tests` is the test tree;
    # neither is application code, and neither may hold imports that matter.
    exempt = {amap.PACKAGE_ROOT, amap.COMPOSITION_ROOT}
    unlayered = {
        src.module
        for src in iter_source_files(backend)
        if amap.layer_of(src.module) is None and not src.module.startswith("backend.tests")
    }
    assert unlayered == exempt, (
        "every module under backend/ must belong to a layer, except the package root "
        f"and the declared composition root ({amap.COMPOSITION_ROOT}). Unexpected: "
        f"{sorted(unlayered - exempt)}"
    )


def test_the_composition_root_holds_no_logic() -> None:
    """Its exemption is justified only while it is pure wiring.

    A composition root that grows branching becomes an unlinted layer — the exact
    reach-around the guardrails exist to prevent. Wiring is a straight line: construct,
    bind, hand over. It needs no branches and no loops.

    Control flow is the check, not arithmetic: `X | Y` type annotations parse as `BinOp`
    and would make an arithmetic ban fire on ordinary typing.
    """
    source = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = (
        ast.If, ast.IfExp, ast.For, ast.While, ast.Try,
        ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
    )
    offenders = [
        type(node).__name__
        for node in ast.walk(tree)
        if isinstance(node, forbidden)
    ]
    assert not offenders, (
        f"the composition root must contain no logic, found: {sorted(set(offenders))}"
    )
