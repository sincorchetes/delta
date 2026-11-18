#!/bin/sh
# How can the daemon tell that an open backup folder is still in use?
#
# Throwaway repository under a temporary directory; nothing of yours is touched.
# Run it in your desktop session (it opens a Files window):   sh scripts/verify_mount_activity.sh
# It makes a 2 GB file by default and needs ~6 GB of free disk under $TMPDIR (BIG_MB=10240 for a longer copy).
# The answers decide whether the daemon can close a forgotten folder safely (docs/roadmap.md, M5):
#   - a program with a file or folder of the mount open        -> /proc/<pid>/fd and /proc/<pid>/cwd
#   - Files showing a folder of the mount, even when still     -> inotify watches in /proc/<pid>/fdinfo
#   - requests served by the `borg mount` process              -> syscr in /proc/<pid>/io
set -u

# A temporary folder in RAM (tmpfs) would fill the memory with the test file: use the disk instead.
base=${TMPDIR:-/tmp}
if [ "$(stat -f -c %T "$base" 2>/dev/null)" = tmpfs ]; then
    base=${XDG_CACHE_HOME:-$HOME/.cache}
    mkdir -p "$base"
fi
work=$(mktemp -d "$base/delta-activity-XXXXXX")
repo=$work/repo
mnt=$work/mnt
data=$work/data
mkdir -p "$mnt" "$data"

export BORG_PASSPHRASE=delta-test
export BORG_BASE_DIR=$work/borg
export BORG_RELOCATED_REPO_ACCESS_IS_OK=yes

mounter=""
holders=""

say()    { printf '%s\n' "$*"; }
ask()    { say ""; say "Q$1. $2"; }
answer() { say "    -> $*"; }
pause()  { printf '    %s ' "$*"; read -r _unused || true; }

cleanup() {
    for pid in $holders "$mounter"; do
        [ -n "$pid" ] && kill "$pid" 2>/dev/null
    done
    fusermount3 -u -z "$mnt" >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT INT TERM

mounted() { grep -q " $mnt fuse" /proc/mounts; }

wait_for() {
    tries=0
    until "$@"; do
        tries=$((tries + 1))
        [ "$tries" -ge 100 ] && return 1
        sleep 0.1
    done
}

# The kernel prints the device of a watched folder as major<<20|minor, in hex.
device_hex() { printf '%x' $(( ($(stat -c %Hd "$1") << 20) | $(stat -c %Ld "$1") )); }

# Programs with a file or their working folder inside the mount.
using_files() {
    found=0
    for proc in /proc/[0-9]*; do
        pid=${proc#/proc/}
        comm=$(cat "$proc/comm" 2>/dev/null) || continue
        for link in "$proc"/fd/* "$proc/cwd"; do
            target=$(readlink "$link" 2>/dev/null) || continue
            case $target in
                "$mnt"|"$mnt"/*)
                    answer "$pid $comm has open: ${target#"$mnt"}"
                    found=1
                    ;;
            esac
        done
    done
    [ "$found" -eq 1 ]
}

# Programs watching (inotify) a folder that lives in the mount.
watching() {
    hex=$(device_hex "$mnt")
    found=0
    for proc in /proc/[0-9]*; do
        pid=${proc#/proc/}
        comm=$(cat "$proc/comm" 2>/dev/null) || continue
        count=0
        for info in "$proc"/fdinfo/*; do
            n=$(grep '^inotify' "$info" 2>/dev/null | grep -c "sdev:$hex ")
            count=$((count + n))
        done
        if [ "$count" -gt 0 ]; then
            answer "$pid $comm watches $count folder(s) of the mount"
            found=1
        fi
    done
    [ "$found" -eq 1 ]
}

requests() { awk '/^syscr/ {print $2}' "/proc/$mounter/io"; }

say "borg: $(borg --version)"
say "work dir: $work"

# The copy of Q6 must last long enough to be seen: a big file (default 2 GB; BIG_MB=10240 for 10 GB).
# It needs about three times its size in free disk space (the file, its backup, and your copy).
# If $TMPDIR (or /tmp) is in RAM, the script works under ~/.cache instead.
big_mb=${BIG_MB:-2048}
free_mb=$(df -Pm "$work" | awk 'NR==2 {print $4}')
if [ "$free_mb" -lt $((big_mb * 3)) ]; then
    say "not enough free space in $(dirname "$work"): ${free_mb} MB free, about $((big_mb * 3)) MB needed."
    say "Point TMPDIR at a bigger disk (not one in RAM), or lower BIG_MB."
    exit 1
fi

say "making a ${big_mb} MB file and backing it up (a minute or two)..."
echo one >"$data/a.txt"
dd if=/dev/urandom of="$data/big.bin" bs=1M count="$big_mb" >/dev/null 2>&1
mkdir -p "$data/sub"
echo two >"$data/sub/b.txt"
borg init --encryption=repokey-blake2 "$repo" >/dev/null 2>&1 || { say "setup: borg init failed"; exit 1; }
borg create "$repo::s1" "$data" >/dev/null 2>&1 || { say "setup: backup failed"; exit 1; }
borg mount -f "$repo::s1" "$mnt" >"$work/mount.log" 2>&1 &
mounter=$!
wait_for mounted || { say "setup: the snapshot did not mount: $(tail -2 "$work/mount.log")"; exit 1; }
inside=$mnt$data

ask 1 "Nothing has touched the folder yet. Does anything show up as using it?"
if using_files || watching; then answer "something is using it (see above)"; else answer "nothing: it reads as unused"; fi

ask 2 "A program holds a file open, and another has the folder as its working folder."
sleep 600 <"$inside/a.txt" &
holders="$holders $!"
(cd "$inside/sub" && exec sleep 600) &
holders="$holders $!"
sleep 0.5
if using_files; then answer "both are seen through /proc/<pid>/fd and /proc/<pid>/cwd"; else answer "NOT seen"; fi
for pid in $holders; do kill "$pid" 2>/dev/null; done
holders=""
sleep 0.3
if using_files; then answer "still shown after they ended (unexpected)"; else answer "gone once they end"; fi

ask 3 "Does the borg mount process count the requests it serves (list, read) and stay still at rest?"
before=$(requests)
sleep 3
rest=$(requests)
ls -R "$mnt" >/dev/null 2>&1
cat "$inside/a.txt" >/dev/null
after=$(requests)
answer "at rest for 3 s: +$((rest - before)) requests; after a listing and a read: +$((after - rest))"

if ! command -v nautilus >/dev/null 2>&1; then
    ask 4 "Files (Nautilus)"
    answer "not installed here: skipped"
    exit 0
fi

ask 4 "A Files window showing a folder of the mount, left alone. Is it seen?"
nautilus --new-window "$inside" >/dev/null 2>&1 &
sleep 4
say "    (a Files window should be open on the folder; do not touch it)"
sleep 6
if watching; then answer "YES: the window is seen as a watcher of the mount"; else answer "NO watcher found"; fi
if using_files; then :; else answer "and no file or working folder of the mount is open by it"; fi

ask 5 "Now go into the 'sub' folder in that window, then back."
pause "Do it, then press Enter."
if watching; then answer "the watcher follows the window"; else answer "NO watcher found"; fi

ask 6 "A long copy out of the mount: is the big file seen as open while it runs?"
say "    In the Files window, copy big.bin (Ctrl+C) and paste it (Ctrl+V) into a folder of your"
say "    disk, outside the mount. Do it now: for the next 120 s the script looks for it."
tries=0
seen=0
while [ "$tries" -lt 240 ]; do
    for proc in /proc/[0-9]*; do
        for link in "$proc"/fd/*; do
            if [ "$(readlink "$link" 2>/dev/null)" = "$inside/big.bin" ]; then
                answer "${proc#/proc/} $(cat "$proc/comm" 2>/dev/null) has big.bin open while copying"
                seen=1
                break 3
            fi
        done
    done
    tries=$((tries + 1))
    sleep 0.5
done
[ "$seen" -eq 1 ] || answer "never seen open in 120 s (no copy started, or it does not hold the file)"
if [ "$seen" -eq 1 ]; then
    pause "Let the copy finish or cancel it, then press Enter."
fi

ask 7 "Close the Files window. Does the mount read as unused again?"
pause "Close the window, wait a few seconds, then press Enter."
if using_files || watching; then answer "something still uses it (see above)"; else answer "nothing: it reads as unused"; fi

say ""
say "Paste this output back: Q2 and Q6 decide whether a long copy is protected,"
say "Q4 and Q5 whether an idle Files window is seen, Q1 and Q7 whether 'unused' is reliable,"
say "and Q3 whether the requests served by borg mount could serve as a second signal."
