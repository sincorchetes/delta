"""What /proc says about an open snapshot folder, on a made-up /proc."""

import os
from types import SimpleNamespace

import pytest

from delta.infrastructure.proc_mount_usage import ProcMountUsage, kernel_device

MOUNT = "/run/user/1000/delta/browse/snapshot"
DEVICE = "2e"  # os.makedev(0, 46) as /proc prints it


@pytest.fixture
def proc(tmp_path):
    root = tmp_path / "proc"
    root.mkdir()
    return root


@pytest.fixture
def usage(proc):
    return ProcMountUsage(str(proc), lambda path: SimpleNamespace(st_dev=os.makedev(0, 46)), own_pid=1)


def program(proc, pid, comm="evince", files=(), cwd=None, watching=()):
    folder = proc / str(pid)
    (folder / "fd").mkdir(parents=True)
    (folder / "fdinfo").mkdir()
    (folder / "comm").write_text(comm + "\n")
    for number, target in enumerate(files):
        os.symlink(target, folder / "fd" / str(number))
    if cwd:
        os.symlink(cwd, folder / "cwd")
    for number, device in enumerate(watching):
        line = f"inotify wd:1 ino:2 sdev:{device} mask:fff ignored_mask:0 fhandle-bytes:8"
        (folder / "fdinfo" / str(10 + number)).write_text(f"pos:\t0\nflags:\t02000000\n{line}\n")
    return folder


def test_the_kernel_prints_a_device_as_major_shifted_by_twenty_bits_and_minor():
    assert kernel_device(os.makedev(0, 46)) == "2e"
    assert kernel_device(os.makedev(8, 1)) == "800001"


def test_with_no_program_around_nothing_uses_the_folder(proc, usage):
    (proc / "cpuinfo").write_text("not a process")
    (proc / "self").mkdir()

    assert usage.users(MOUNT) == []


def test_a_file_open_in_the_folder_counts(proc, usage):
    program(proc, 7, files=["/dev/null", MOUNT + "/video.mkv"])

    assert usage.users(MOUNT) != []


def test_it_says_who_uses_the_folder_and_how(proc, usage):
    program(proc, 8, comm="nautilus", watching=[DEVICE])
    program(proc, 7, comm="evince", files=[MOUNT + "/a.pdf"])

    assert usage.users(MOUNT) == [
        "evince (7): has a file or folder open",
        "nautilus (8): watches a folder",
    ]


def test_the_folder_itself_open_counts(proc, usage):
    program(proc, 7, files=[MOUNT])

    assert usage.users(MOUNT) != []


def test_a_working_folder_inside_counts(proc, usage):
    program(proc, 7, cwd=MOUNT + "/home/ana")

    assert usage.users(MOUNT) != []


def test_files_elsewhere_do_not_count_not_even_a_folder_whose_name_starts_the_same(proc, usage):
    program(proc, 7, files=["/home/ana/a.txt", MOUNT + "2/b.txt"], cwd="/home/ana")

    assert usage.users(MOUNT) == []


def test_a_window_watching_a_folder_of_the_mount_counts_even_if_nothing_moves(proc, usage):
    program(proc, 7, comm="nautilus", watching=["1", DEVICE])

    assert usage.users(MOUNT) != []


def test_a_watch_on_another_filesystem_does_not_count(proc, usage):
    program(proc, 7, comm="nautilus", watching=["1", "2f"])

    assert usage.users(MOUNT) == []


def test_the_gvfs_daemons_always_watch_the_top_of_a_mount_so_they_never_count(proc, usage):
    program(proc, 7, comm=".gvfsd-trash-wr", watching=[DEVICE], files=[MOUNT + "/x"])
    program(proc, 8, comm="gvfsd-metadata", watching=[DEVICE])

    assert usage.users(MOUNT) == []


def test_the_daemon_itself_is_not_a_user_of_its_own_folder(proc, usage):
    program(proc, 1, comm="python3", files=[MOUNT + "/x"])

    assert usage.users(MOUNT) == []


def test_a_program_that_ends_while_it_is_being_looked_at_is_not_a_problem(proc, usage):
    (proc / "9").mkdir()  # no comm, no fd: gone
    program(proc, 10, comm="evince")
    os.rmdir(proc / "10" / "fd")  # fd list gone, comm still there

    assert usage.users(MOUNT) == []


def test_what_cannot_be_read_is_skipped(proc, usage):
    folder = program(proc, 7, files=[], watching=[DEVICE])
    (folder / "fd" / "3").write_text("a file, not a link: readlink fails like for a closed fd")
    (folder / "fdinfo" / "4").mkdir()  # reading it fails like for an fd that vanished

    assert usage.users(MOUNT) != []  # the readable watch still counts


def test_by_default_it_reads_the_real_proc_and_leaves_the_daemon_itself_out():
    usage = ProcMountUsage()

    assert usage._proc == "/proc" and usage._own == str(os.getpid())
