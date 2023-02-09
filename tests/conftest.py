from hypothesis import settings
from hypothesis.database import DirectoryBasedExampleDatabase, MultiplexedDatabase
from hypofuzz.database import GitHubArtifactDatabase
import os

local = DirectoryBasedExampleDatabase("/tmp/hypothesis/examples/")
shared = GitHubArtifactDatabase("agucova", "hypofuzz")

settings.register_profile("ci", database=local)
settings.register_profile(
    "dev", database=MultiplexedDatabase(local, shared)
)
settings.load_profile("ci" if os.environ.get("CI") else "dev")
