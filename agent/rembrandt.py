"""Compatibility shim for ai-eggs.

Rembrandt was moved to freelance-agent/.agent/agents/rembrandt/.
This shim re-exports the public API so legacy ai-eggs modules
(content_machine_orchestrator, sandbox_pipeline, sandbox_live_feed_demo)
keep working without code changes.
"""

import importlib.util
import os
import sys

_GLOBAL_PKG = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "freelance-agent", ".agent", "agents", "rembrandt",
    )
)

_spec = importlib.util.spec_from_file_location(
    "rembrandt_global_pkg",
    os.path.join(_GLOBAL_PKG, "__init__.py"),
    submodule_search_locations=[_GLOBAL_PKG],
)
_pkg = importlib.util.module_from_spec(_spec)
sys.modules["rembrandt_global_pkg"] = _pkg
_spec.loader.exec_module(_pkg)

RembrandtDesigner = _pkg.RembrandtDesigner
generate_component = _pkg.generate_component
generate_design_md = _pkg.generate_design_md
render_design_md = _pkg.render_design_md
leonardo_generate = _pkg.leonardo_generate
download_image = _pkg.download_image
INCUBIRD_DEFAULT = _pkg.INCUBIRD_DEFAULT
COMPONENT_TYPES = _pkg.COMPONENT_TYPES
load_brand = _pkg.load_brand
BrandSystem = _pkg.BrandSystem
DesignToken = _pkg.DesignToken
