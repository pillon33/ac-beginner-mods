"""Guard against syntax that crashes in AC's embedded Python 3.3.

Modern Python happily runs the in-game apps' pure modules in tests,
so a stray f-string would pass every other test and only fail when
AC loads the app. This walks the AST of every file under apps/python
and rejects the 3.6+ syntax that's easiest to slip in by habit.
"""

import ast
import glob
import os

import pytest

APPS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apps", "python")

FORBIDDEN_NODES = {
    "JoinedStr": "f-string (3.6+)",
    "AnnAssign": "annotated assignment (3.6+)",
    "NamedExpr": "walrus operator (3.8+)",
    "AsyncFunctionDef": "async def (3.5+)",
    "Await": "await (3.5+)",
}

APP_SOURCES = sorted(glob.glob(os.path.join(APPS_DIR, "**", "*.py"), recursive=True))


@pytest.mark.parametrize("path", APP_SOURCES, ids=lambda p: os.path.relpath(p, APPS_DIR))
def test_app_source_is_python33_compatible(path):
    with open(path, encoding="utf-8") as source:
        tree = ast.parse(source.read(), filename=path)

    problems = [
        "line {}: {}".format(node.lineno, FORBIDDEN_NODES[type(node).__name__])
        for node in ast.walk(tree)
        if type(node).__name__ in FORBIDDEN_NODES
    ]
    assert not problems, "{} uses syntax AC's Python 3.3 can't run:\n  {}".format(
        path, "\n  ".join(problems))
