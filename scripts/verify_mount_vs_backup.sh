#!/bin/sh
# Opening a backup while another one is being made: what does borg allow, and how do we get out?
#
# Throwaway repository under a temporary directory; nothing of yours is touched.
# Run it inside `devenv shell`:   sh scripts/verify_mount_vs_backup.sh
# Each question prints its answer and the exact message borg gave. These answers decide the
# design of `MountSnapshot` (docs/roadmap.md, M5): "browsing wins over backing up".
set -u

work=$(mktemp -d "${TMPDIR:-/tmp}/delta-mountvs-XXXXXX")
repo=$work/repo
mnt=$work/mnt
data=$work/data
feed=$work/feed
mkdir -p "$mnt" "$data"
mkfifo "$feed"

export BORG_PASSPHRASE=delta-test
export BORG_BASE_DIR=$work/borg
export BORG_RELOCATED_REPO_ACCESS_IS_OK=yes

creator=""
feeder=""
mounter=""
holder=""
probe=0

say()    { printf '%s\n' "$*"; }
ask()    { say ""; say "Q$1. $2"; }
answer() { say "    -> $*"; }
quote()  { say "       borg said: $(printf '%s' "$1" | tail -2 | tr '\n' ' ')"; }

running() { [ -n "$1" ] && [ -d "/proc/$1" ] && ! grep -q '^State:[[:space:]]*Z' "/proc/$1/status" 2>/dev/null; }
stopped() { ! running "$1"; }
mounted() { grep -q " $mnt fuse" /proc/mounts; }
unmounted() { ! mounted; }
locked()  { [ -e "$repo/lock.exclusive" ]; }

# Polls a condition for up to ~10 s.
wait_for() {
    tries=0
    until "$@"; do
        tries=$((tries + 1))
        [ "$tries" -ge 100 ] && return 1
        sleep 0.1
    done
}

# The counter moves outside `$(...)`: inside it the increment would be lost with the subshell.
next_probe() { probe=$((probe + 1)); }
can_back_up() { borg create --lock-wait 3 "$repo::probe$probe" "$data" 2>&1; }

cleanup() {
    for pid in "$holder" "$creator" "$feeder" "$mounter"; do
        [ -n "$pid" ] && kill -KILL "$pid" 2>/dev/null
    done
    borg umount "$mnt" >/dev/null 2>&1 || fusermount3 -u -z "$mnt" >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT INT TERM

say "borg: $(borg --version)"
say "work dir: $work"

echo one >"$data/a.txt"
dd if=/dev/urandom of="$data/video.bin" bs=1M count=50 >/dev/null 2>&1
borg init --encryption=repokey-blake2 "$repo" >/dev/null 2>&1 || { say "setup: borg init failed"; exit 1; }
borg create "$repo::s1" "$data" >/dev/null 2>&1 || { say "setup: first backup failed"; exit 1; }

# A backup that stays running for as long as we want: it reads an endless stream from stdin.
# (A big file would race: the backup could finish before the mount is tried.)
# The stream must keep FLOWING: borg acts on SIGINT between chunks, so a backup stuck waiting
# for input never notices it. `yes` repeats itself, so deduplication keeps the repository tiny.
# `env --default-signal` matters: a shell starts background jobs with SIGINT ignored, and the
# daemon does not, so without it Q2 would test something Delta never does.
yes >"$feed" &
feeder=$!
env --default-signal=INT borg create "$repo::held" - <"$feed" >"$work/held.log" 2>&1 &
creator=$!
wait_for locked || sleep 2
if stopped "$creator"; then
    say "setup: the long backup did not stay running: $(cat "$work/held.log")"
    exit 1
fi

ask 1 "A backup is RUNNING. Can a snapshot be mounted without stopping it?"
if out=$(borg mount --lock-wait 1 "$repo" "$mnt" 2>&1); then
    if running "$creator"; then
        answer "YES: it mounted and the backup kept running. Interrupting is not needed to open."
    else
        answer "UNCLEAR: it mounted, but the backup had already ended. Run the script again."
    fi
    borg umount "$mnt" >/dev/null 2>&1 || fusermount3 -u "$mnt" >/dev/null 2>&1 || true
    wait_for unmounted || true
else
    answer "NO: the mount is refused. The backup must be interrupted first (as designed)."
    quote "$out"
fi

ask 2 "How long does an interrupted backup (SIGINT) take to let go of the repository?"
start=$(date +%s)
kill -INT "$creator"
if wait_for stopped "$creator"; then
    wait "$creator"
    code=$?
    answer "it exited with code $code after ~$(($(date +%s) - start)) s"
    answer "last lines of the backup: $(tail -2 "$work/held.log" | tr '\n' ' ')"
else
    answer "STILL RUNNING after 10 s with one SIGINT; sending a second one"
    kill -INT "$creator"
    if wait_for stopped "$creator"; then
        wait "$creator"
        answer "the second SIGINT ended it: code $? after ~$(($(date +%s) - start)) s in total"
    else
        answer "STILL RUNNING after two SIGINT and 20 s: it needs SIGTERM or SIGKILL"
    fi
fi
kill "$feeder" 2>/dev/null
creator=""

ask 3 "Right after the interruption, does the mount work and read a file back?"
env --default-signal=INT borg mount -f "$repo" "$mnt" >"$work/mount.log" 2>&1 &
mounter=$!
if wait_for mounted; then
    file=$(find "$mnt" -name a.txt 2>/dev/null | head -1)
    if [ -n "$file" ] && [ "$(cat "$file")" = one ]; then
        answer "YES: mounted and a.txt reads back"
    else
        answer "PARTLY: mounted, but a.txt did not read back"
    fi
else
    answer "NO: $(cat "$work/mount.log")"
    say ""
    say "Without a mount the remaining questions cannot be answered. Stopping."
    exit 1
fi

ask 4 "A snapshot is OPEN. Is the hourly backup blocked? (the case that makes it wait)"
if next_probe && out=$(can_back_up); then
    answer "NO: the backup ran with the snapshot mounted"
else
    answer "YES: the backup cannot start while a snapshot is mounted"
    quote "$out"
fi

ask 5 "Another program holds a file of the snapshot open (a video player). Does unmounting work?"
big=$(find "$mnt" -name video.bin 2>/dev/null | head -1)
sleep 600 <"$big" &
holder=$!
sleep 0.5
if out=$(borg umount "$mnt" 2>&1) && wait_for unmounted; then
    answer "YES: it unmounted with the file still open"
else
    answer "NO: the mount stays while the file is open"
    quote "$out"
fi

if mounted; then
    ask 6 "Then: stopping the mount process (SIGTERM), as the daemon would on suspend or lock?"
    kill -TERM "$mounter"
    if wait_for stopped "$mounter"; then
        answer "the mount process exited"
    else
        answer "the mount process is STILL RUNNING after 10 s"
    fi
    if mounted; then answer "the folder is STILL mounted"; else answer "the folder is unmounted"; fi
    if next_probe && out=$(can_back_up); then
        answer "a backup CAN run now: the repository is free"
    else
        answer "a backup is STILL blocked"
        quote "$out"
    fi

    if mounted; then
        ask 7 "Last resort: a lazy unmount (fusermount3 -u -z) with the file still open?"
        fusermount3 -u -z "$mnt" 2>&1 | sed 's/^/       /'
        if wait_for unmounted; then answer "the folder is unmounted"; else answer "STILL mounted"; fi
        wait_for stopped "$mounter" && answer "the mount process exited" || answer "the mount process is still running"
        if next_probe && out=$(can_back_up); then
            answer "a backup CAN run now"
        else
            answer "a backup is STILL blocked until the file is closed"
            quote "$out"
        fi
    fi
fi

kill "$holder" 2>/dev/null
holder=""

ask 8 "Once everything is closed, is the repository back to normal?"
wait_for stopped "$mounter" || true
if next_probe && out=$(can_back_up); then
    answer "YES: a backup runs"
else
    answer "NO"
    quote "$out"
fi
if out=$(borg list --consider-checkpoints --short "$repo" 2>&1); then
    answer "archives left behind: $(printf '%s' "$out" | tr '\n' ' ')"
fi

ask 9 "A real backup in the middle of ONE huge file (20 GB): how long does one SIGINT take?"
# Sparse: it takes no disk space and deduplicates to almost nothing, but borg still has to
# read all of it, so the signal arrives mid-file. This is the Matroska / Blu-ray / RAW case.
mkdir "$work/huge"
truncate -s 20G "$work/huge/film.mkv"
env --default-signal=INT borg create "$repo::huge" "$work/huge" >"$work/huge.log" 2>&1 &
creator=$!
sleep 3
if stopped "$creator"; then
    answer "UNCLEAR: the backup ended in under 3 s, before the signal"
else
    start=$(date +%s)
    kill -INT "$creator"
    rounds=0
    until wait_for stopped "$creator" || [ "$rounds" -ge 5 ]; do rounds=$((rounds + 1)); done
    if stopped "$creator"; then
        wait "$creator"
        answer "ONE SIGINT ended it: code $? after ~$(($(date +%s) - start)) s"
    else
        answer "STILL RUNNING ~60 s after one SIGINT; sending a second one"
        kill -INT "$creator"
        if wait_for stopped "$creator"; then
            wait "$creator"
            answer "the second SIGINT ended it: code $?"
        else
            answer "STILL RUNNING after the second SIGINT"
        fi
    fi
    answer "last lines of the backup: $(tail -2 "$work/huge.log" | tr '\n' ' ')"
    if out=$(borg list --consider-checkpoints --short "$repo" 2>&1); then
        answer "archives now: $(printf '%s' "$out" | tr '\n' ' ')"
    fi
fi

say ""
say "Paste this output back: Q1 decides whether opening interrupts a backup at all,"
say "Q2-Q3 how fast the window can open, and Q5-Q7 what closing it by force needs."
