"""
core/project_mapper
ProjectMapper — code-aware ingestion layer for AethvionDB.

Scans an entire software project (Python AST + optional LLM enrichment)
and populates a designated AethvionDB database with a rich knowledge graph
of modules, classes, functions, dependencies, and their relationships.

Quick start
-----------
  POST /api/project-mapper/preview?project_root=/path/to/project
  POST /api/project-mapper/scan   body: { project_root, db, enrich }
  GET  /api/project-mapper/scan/status?db=my_project
  GET  /api/project-mapper/stats?db=my_project
"""
