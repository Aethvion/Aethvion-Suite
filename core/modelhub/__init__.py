"""
core/modelhub — one registry and one call path for every kind of model.

    from core.modelhub import hub, registry
    registry.list_endpoints("mesh.generate")
    hub.invoke("demo:mesh", "mesh.generate", prompt="a crate")
"""
from . import capabilities, registry  # noqa: F401
