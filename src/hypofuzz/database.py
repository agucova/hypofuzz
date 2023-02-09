import shutil
import tempfile
from os import getenv

import requests
from hypothesis.configuration import mkdir_p, storage_directory
from hypothesis.database import DirectoryBasedExampleDatabase


class GitHubArtifactDatabase(DirectoryBasedExampleDatabase):
    """
    A database that reads from a GitHub artifact.

    This provides read-only access to a database produced by CI and requires a GitHub token (set by the `GH_TOKEN` environment variable).
    """

    def __init__(self, owner: str, repo: str, artifact_name: str = "hypofuzz-example-db"):
        self.owner = owner
        self.repo = repo
        self.artifact_name = artifact_name

        # Get the GitHub token from the environment
        # It's unnecessary to use a token if the repo is public
        self.token = getenv("GH_TOKEN")

        # Get the latest artifact from the GitHub API
        try:
            res = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2023-02-09",
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
            raise RuntimeError(
                "Could not get the latest artifact from GitHub. "
                "Check that the repository exists and that the token is valid."
            )

        artifact = sorted(
            filter(lambda a: a["name"] == artifact_name, artifacts),
            key=lambda a: a["created_at"],
        )[-1]

        # Download and extract the artifact into .hypothesis/ci
        with tempfile.NamedTemporaryFile() as f:
            # Download the artifact
            try:
                req = requests.get(
                    artifact["archive_download_url"],
                    headers={
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2023-02-09",
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
                    "Check that the repository exists and that the token is valid."
                )

            f.write(req.content)

            # Extract the artifact into .hypothesis/ci
            mkdir_p(storage_directory("ci"))
            shutil.unpack_archive(f.name, storage_directory("ci"), "zip")

        super().__init__(storage_directory("ci"))

    def __repr__(self) -> str:
        return f"GitHubArtifactDatabase(owner={self.owner}, repo={self.repo}, artifact_name={self.artifact_name})"

    # Now we disable the write methods
    def save(self, key: bytes, value: bytes) -> None:
        pass

    def delete(self, key: bytes, value: bytes) -> None:
        pass
