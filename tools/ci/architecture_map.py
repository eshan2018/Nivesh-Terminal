"""The machine-checkable model of the frozen architecture.

This module is the single source of truth the CI guardrails read. It encodes:

- doc 03's layer stack and its dependency direction (ADR-0002),
- doc 06's vendor-isolation rule (ADR-0005),
- ADR-0003's module-owned-schema rule.

Changing an edge here is changing the architecture — which per the frozen
governance requires an ADR, not an edit to this file alone.
"""
from __future__ import annotations

PACKAGE_ROOT = "backend"
KERNEL = "backend.platform"

# Each layer package -> the OTHER layer packages it may import.
# The kernel (`backend.platform`) and a package's own subpackages are ALWAYS allowed
# and are therefore omitted from these sets.
ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "backend.platform": frozenset(),
    "backend.providers.ports": frozenset(),
    "backend.providers": frozenset({"backend.providers.ports"}),
    "backend.domain.model": frozenset(),
    "backend.domain": frozenset({"backend.domain.model"}),
    "backend.ingestion": frozenset({"backend.providers.ports", "backend.domain.model"}),
    # Features are the ONLY layer permitted to reach the domain repositories (doc 08).
    "backend.features": frozenset({"backend.domain.model", "backend.domain"}),
    # Engines consume features and other engines' results — never repositories (doc 08).
    "backend.analytics": frozenset({"backend.domain.model", "backend.features"}),
    # The API projects analytics results into DTOs (doc 10); it does not reach L6/L5 repos.
    "backend.api": frozenset({"backend.domain.model", "backend.analytics"}),
    # Orchestration is the pipeline coordinator (doc 16): it may drive the layers below it,
    # but nothing imports it.
    "backend.orchestration": frozenset({
        "backend.providers.ports",
        "backend.ingestion",
        "backend.domain",
        "backend.domain.model",
        "backend.features",
        "backend.analytics",
    }),
}

# ── The composition root (ED-011) ─────────────────────────────────────────────
# Every layered application needs one place where concrete implementations are
# constructed and injected. Principle 5 (doc 02) governs what a layer may *depend
# on* — "only the layer directly beneath it, via that layer's published contract" —
# and is silent on who *builds* objects; being handed a constructed collaborator is
# not a reach-around. So the entry point may import across layers **solely to
# construct and wire**, and must contain no domain, analytics, or serving logic.
#
# This is declared rather than left implicit. `layer_of` returns None for it, and the
# dependency lint skips modules that belong to no layer — so without this constant the
# exemption would be an unexamined blind spot rather than a decision. The guardrail
# test asserts this is the *only* module in `backend/` outside the layer graph, which
# is what stops a second, undeclared one appearing later.
COMPOSITION_ROOT = "backend.main"

# Layer packages ordered deepest-first, so longest-prefix resolution is unambiguous
# (e.g. `backend.providers.ports` wins over `backend.providers`).
_LAYERS_DEEPEST_FIRST = sorted(ALLOWED_IMPORTS, key=lambda p: p.count("."), reverse=True)


def layer_of(module: str) -> str | None:
    """Return the layer package that owns ``module`` by longest dotted-prefix match."""
    for layer in _LAYERS_DEEPEST_FIRST:
        if module == layer or module.startswith(layer + "."):
            return layer
    return None


def import_permitted(importer_layer: str, target_layer: str) -> bool:
    """Whether a module in ``importer_layer`` may import one in ``target_layer``."""
    if target_layer == KERNEL:
        return True
    if target_layer == importer_layer:
        return True
    if target_layer.startswith(importer_layer + "."):  # own subpackage
        return True
    return target_layer in ALLOWED_IMPORTS.get(importer_layer, frozenset())


# ── Vendor isolation (doc 06 / ADR-0005) ──────────────────────────────────────
# Vendor token -> the ONLY package prefix in which it may legitimately appear.
VENDOR_ALLOWED_PREFIX: dict[str, str] = {
    "yfinance": "backend.providers.yfinance",
    "alpha_vantage": "backend.providers.alpha_vantage",
    "alphavantage": "backend.providers.alpha_vantage",
}


def vendor_home(module: str, token: str) -> bool:
    """Whether ``module`` is the sanctioned adapter home for vendor ``token``."""
    prefix = VENDOR_ALLOWED_PREFIX[token]
    return module == prefix or module.startswith(prefix + ".")


# ── Module-owned schemas (ADR-0003) ───────────────────────────────────────────
DOMAIN_ROOT = "backend.domain"
# `model` is the shared canonical vocabulary (doc 04), not a data-owning module.
DOMAIN_SHARED: frozenset[str] = frozenset({"backend.domain.model"})


def domain_module_of(module: str) -> str | None:
    """Return the data-owning domain module (e.g. ``backend.domain.market_data``) that
    owns ``module``, or ``None`` if ``module`` is not inside a data-owning domain module
    (which includes the shared ``backend.domain.model`` vocabulary)."""
    if not (module == DOMAIN_ROOT or module.startswith(DOMAIN_ROOT + ".")):
        return None
    tail = module[len(DOMAIN_ROOT) + 1:]
    if not tail:
        return None
    candidate = f"{DOMAIN_ROOT}.{tail.split('.')[0]}"
    if candidate in DOMAIN_SHARED:
        return None
    return candidate
