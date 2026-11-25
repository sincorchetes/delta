"""Pure builders of borg argv lists (never a shell string)."""

from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy


def init(repo: Repository) -> list[str]:
    return ["borg", "init", f"--encryption={repo.encryption.value}", repo.location]


CHECKPOINT_SECONDS = 300  # borg default is 1800: an interruption loses at most this much work


def create(repo: Repository, archive: str, job: BackupJob) -> list[str]:
    argv = [
        "borg", "create", "--json", "--stats", "--progress", "--log-json",
        f"--checkpoint-interval={CHECKPOINT_SECONDS}",
    ]
    for pattern in job.excludes:
        argv += ["--exclude", pattern]
    return argv + [f"{repo.location}::{archive}", *job.sources]


def break_lock(repo: Repository) -> list[str]:
    return ["borg", "break-lock", repo.location]


def check(repo: Repository) -> list[str]:
    """The consistency of the repository itself: the check of the data of every backup takes far longer."""
    return ["borg", "check", "--repository-only", repo.location]


def list_archives(repo: Repository) -> list[str]:
    return ["borg", "list", "--json", repo.location]


def repository_id(repo: Repository) -> list[str]:
    """One archive is enough: the answer carries the identifier of the repository, and a long list is slow."""
    return ["borg", "list", "--json", "--last", "1", repo.location]


def list_path(repo: Repository, archive: str, path: str) -> list[str]:
    return ["borg", "list", "--json-lines", f"{repo.location}::{archive}", path.lstrip("/")]


def mount(repo: Repository, archive: str, mountpoint: str) -> list[str]:
    """In the foreground, so the process that holds the mount is ours to stop."""
    return ["borg", "mount", "-f", f"{repo.location}::{archive}", mountpoint]


def lazy_unmount(mountpoint: str) -> list[str]:
    """Detach even if a program still holds a file open (a plain unmount is refused then)."""
    return ["fusermount3", "-u", "-z", mountpoint]


def extract(repo: Repository, archive: str, paths: tuple[str, ...]) -> list[str]:
    return ["borg", "extract", f"{repo.location}::{archive}", *(p.lstrip("/") for p in paths)]


def prune(repo: Repository, policy: RetentionPolicy) -> list[str]:
    if not policy.keeps_anything:
        raise ValueError("refusing to prune with a policy that keeps nothing")
    argv = ["borg", "prune"]
    for key, value in policy.as_dict().items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    return argv + [repo.location]
