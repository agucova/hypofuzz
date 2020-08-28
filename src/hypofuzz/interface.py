"""CLI and Python API for the fuzzer."""
import io
from contextlib import redirect_stdout
from typing import TYPE_CHECKING, Iterable, List, NoReturn, Tuple

import click
import psutil
import pytest
from hypothesis.extra.cli import main as hypothesis_cli_root

if TYPE_CHECKING:
    from .hy import FuzzProcess


class _ItemsCollector:
    """A pytest plugin which grabs all the fuzzable tests at the end of collection."""

    def __init__(self) -> None:
        self.fuzz_targets: List["FuzzProcess"] = []

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        from .hy import FuzzProcess

        for item in session.items:
            # If the test takes a fixture, we skip it - the fuzzer doesn't have
            # pytest scopes, so we just can't support them.  TODO: note skips.
            if item._request._fixturemanager.getfixtureinfo(
                node=item, func=item.function, cls=None
            ).name2fixturedefs:
                continue
            # For parametrized tests, we have to pass the parametrized args into
            # wrapped_test.hypothesis.get_strategy() to avoid trivial TypeErrors
            # from missing required arguments.
            extra_kw = item.callspec.params if hasattr(item, "callspec") else {}
            # Wrap it up in a FuzzTarget and we're done!
            fuzz = FuzzProcess.from_hypothesis_test(
                item.obj, nodeid=item.nodeid, extra_kw=extra_kw
            )
            self.fuzz_targets.append(fuzz)


def _get_hypothesis_tests_with_pytest(args: Iterable[str]) -> Iterable["FuzzProcess"]:
    """Find the hypothesis-only test functions run by pytest.

    This basically uses `pytest --collect-only -m hypothesis $args`.
    """
    collector = _ItemsCollector()
    with redirect_stdout(io.StringIO()):
        pytest.main(
            args=["--collect-only", "-m=hypothesis", *args],
            plugins=[collector],
        )
    return collector.fuzz_targets


@hypothesis_cli_root.command()  # type: ignore
@click.option(
    "-n",
    "--numprocesses",
    type=click.IntRange(0, None),
    metavar="NUM",
    # we match the -n auto behaviour of pytest-xdist by default
    default=psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
    help="default: all available cores",
)
@click.option(
    "--dashboard/--no-dashboard",
    default=True,
    help="serve / don't serve a live dashboard page",
)
@click.option(
    "--port",
    type=click.IntRange(0, 65535),
    default=0,
    metavar="PORT",
    help="Optional port for the dashboard (if any)",
)
@click.option(
    "--unsafe",
    is_flag=True,
    help="Allow concurrent execution of each test",
)
@click.argument(
    "pytest_args",
    nargs=-1,
    metavar="[-- PYTEST_ARGS]",
)
def fuzz(
    numprocesses: int,
    dashboard: bool,
    port: int,
    unsafe: bool,
    pytest_args: Tuple[str, ...],
) -> NoReturn:
    """[hypofuzz] runs tests with an adaptive coverage-guided fuzzer.

    Unrecognised arguments are passed through to `pytest` to select the tests
    to run, with the additional constraint that only tests using Hypothesis
    but not any pytest fixtures can be fuzzed.

    This process will run forever unless stopped with e.g. ctrl-C.
    """
    # Before doing anything with our arguments, we'll check that none
    # of HypoFuzz's arguments will be passed on to pytest instead.
    misplaced = set().union(*(p.opts for p in fuzz.params)).intersection(pytest_args)
    if misplaced:
        plural = "s" * (len(misplaced) > 1)
        names = ", ".join(map(repr, misplaced))
        raise click.UsageError(
            f"fuzzer option{plural} {names} would be passed to pytest instead"
        )

    # With our arguments validated, it's time to actually do the work.
    from .hy import fuzz_several

    tests = _get_hypothesis_tests_with_pytest(pytest_args)
    if not tests:
        raise click.UsageError("No property-based tests were collected")
    if numprocesses > len(tests) and not unsafe:
        numprocesses = len(tests)

    if dashboard:
        # TODO: start serving a live html dashboard on `port`
        # (and stop printing stats!)
        print(f"\n\tNow serving dashboard at  http://localhost:{port}\n")  # noqa
    testnames = "\n    ".join(t.nodeid for t in tests)
    print(f"using up to {numprocesses} processes to fuzz:\n    {testnames}\n")  # noqa

    fuzz_several(*tests, numprocesses=numprocesses)
    raise NotImplementedError("unreachable")
