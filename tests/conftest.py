from hypothesis import settings
from hypothesis.database import DirectoryBasedExampleDatabase, MultiplexedDatabase
from hypofuzz.database import GitHubArtifactDatabase
import os

local = DirectoryBasedExampleDatabase(".hypothesis/examples")
shared = GitHubArtifactDatabase("agucova", "hypofuzz")

settings.register_profile("ci", database=local)
settings.register_profile("dev", database=MultiplexedDatabase(local, shared))
if os.environ.get("CI"):
    settings.load_profile("ci")
    print("🤖 Running on CI mode")
else:
    settings.load_profile("dev")
    print("👨‍💻 Running on dev mode")
