"""The `pangloss` command. A script loads a project's settings and apps with `load_project()`"""

lazy from pangloss_cli.project import Project, load_project

__all__ = ["load_project", "Project"]
