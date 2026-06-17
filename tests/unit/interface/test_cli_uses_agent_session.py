"""Guard test for architecture invariant I2 (single assembly path).

The CLI previously hand-rolled LLM / Tools / Runtime per execution mode and
thereby skipped the CPA module hooks (M1-M6) that live inside the shared
composition root. P1-b routed all three CLI modes through AgentSession.create.
This test locks that in: the CLI entry must not reconstruct the assembly that
would bypass the composition root.
"""

import inspect

from pentestagent.interface import cli


def test_run_cli_routes_through_agent_session():
    src = inspect.getsource(cli.run_cli)

    # Must build everything through the single facade...
    assert "AgentSession.create" in src

    # ...and must NOT hand-roll the pieces the composition root owns, or the
    # CPA hooks get skipped again (the bug this test guards).
    assert "build_runtime(" not in src, "CLI must not build runtime directly"
    assert "PentestAgentAgent(" not in src, "CLI must not construct the agent directly"
    assert "get_all_tools(" not in src, "CLI must not load tools directly"
    assert "LLM(model=" not in src, "CLI must not construct an LLM outside the root"


def test_run_cli_does_not_import_assembly_primitives():
    """The function-local imports should no longer pull assembly primitives."""
    src = inspect.getsource(cli.run_cli)
    assert "from ..session import AgentSession" in src
    assert "import RAGEngine" not in src
    assert "build_runtime" not in src
