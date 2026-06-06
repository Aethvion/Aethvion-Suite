"""
Allows the package to be run as:
    python -m core.project_mapper [args...]

Equivalent to:
    python -m core.project_mapper.mcp_server [args...]
"""
from .mcp_server import main

main()
