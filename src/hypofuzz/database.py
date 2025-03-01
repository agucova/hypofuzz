import shutil
import tempfile
from os import getenv

import requests
from hypothesis.configuration import mkdir_p, storage_directory
from hypothesis.database import DirectoryBasedExampleDatabase


class GitHubArtifactDatabase(DirectoryBasedExampleDatabase):
    """
    A database that reads from a GitHub artifact.

    This provides read-only access to a database produced by CI and requires a GitHub token (set by the `GITHUB_TOKEN` environment variable).
    For mono-repo support, you can provide an unique `artifact_name` (e.g. `hypofuzz-example-db-branch`).
    """

    def __init__(
        self, owner: str, repo: str, artifact_name: str = "hypofuzz-example-db"
    ):
        self.owner = owner
        self.repo = repo
        self.artifact_name = artifact_name

        # Get the GitHub token from the environment
        # It's unnecessary to use a token if the repo is public
        self.token = getenv("GITHUB_TOKEN")

        # We want to be lazy per conftest initialization
        self._artifact_downloaded = False

    def __repr__(self) -> str:
        return f"GitHubArtifactDatabase(owner={self.owner}, repo={self.repo}, artifact_name={self.artifact_name})"

    def _fetch_artifact(self) -> None:
        if self._artifact_downloaded:
            return

        # Get the latest artifact from the GitHub API
        try:
            res = requests.get(
                f"https://api.github.com/repos/{self.owner}/{self.repo}/actions/artifacts",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28 ",
                    "Authorization": f"Bearer {self.token}",
                },
            )
            res.raise_for_status()
            artifacts: list[dict] = res.json()["artifacts"]
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Could not connect to GitHub to get the latest artifact."
            )
        except requests.exceptions.HTTPError:
            # TODO: Be more granular
            raise RuntimeError(
                "Could not get the latest artifact from GitHub. "
                "Check that the repository exists and that you've provided a valid token (GITHUB_TOKEN)."
            )

        # Get the latest artifact from the list
        artifact = sorted(
            filter(lambda a: a["name"] == self.artifact_name, artifacts),
            key=lambda a: a["created_at"],
        )[-1]

        # Download and extract the artifact into .hypothesis/ci
        with tempfile.NamedTemporaryFile() as f:
            try:
                req = requests.get(
                    artifact["archive_download_url"],
                    headers={
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "Authorization": f"Bearer {self.token}",
                    },
                    stream=True,
                    allow_redirects=True,
                )
                req.raise_for_status()
            except requests.exceptions.ConnectionError:
                raise RuntimeError(
                    "Could not connect to GitHub to download the artifact."
                )
            except requests.exceptions.HTTPError:
                raise RuntimeError(
                    "Could not get the latest artifact from GitHub. "
                    "Check that the repository exists and that you've provided a valid token (GITHUB_TOKEN)."
                )

            f.write(req.content)

            # Extract the artifact into .hypothesis/ci
            mkdir_p(storage_directory("ci"))
            shutil.unpack_archive(f.name, storage_directory("ci"), "zip")

        super().__init__(storage_directory("ci"))
        self._artifact_downloaded = True

    def fetch(self, key: bytes):
        self._fetch_artifact()
        # Delegate all IO to DirectoryBasedExampleDatabase
        return super().fetch(key)

    # Read-only interface
    def save(self, key: bytes, value: bytes) -> None:
        pass

    def delete(self, key: bytes, value: bytes) -> None:
        pass
