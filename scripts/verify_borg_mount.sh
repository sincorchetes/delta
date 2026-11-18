#!/bin/sh
# Does `borg mount` work on this machine, and what does a mounted repository do to a backup?
#
# Throwaway repository under a temporary directory; nothing of yours is touched.
# Run it inside `devenv shell`:   sh scripts/verify_borg_mount.sh
# It prints PASS/FAIL per step and the exact messages borg gave, which is what M5 depends on.
set -u

work=$(mktemp -d "${TMPDIR:-/tmp}/delta-mount-XXXXXX")
repo=$work/repo
mnt=$work/mnt
data=$work/data
mkdir -p "$mnt" "$data"

export BORG_PASSPHRASE=delta-test
export BORG_BASE_DIR=$work/borg
export BORG_RELOCATED_REPO_ACCESS_IS_OK=yes

pass=0
fail=0
say() { printf '%s\n' "$*"; }
ok()  { pass=$((pass + 1)); say "[PASS] $*"; }
bad() { fail=$((fail + 1)); say "[FAIL] $*"; }

cleanup() {
    borg umount "$mnt" >/dev/null 2>&1 || fusermount3 -u "$mnt" >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT INT TERM

say "borg: $(borg --version)"
say "work dir: $work"
say ""

echo one >"$data/a.txt"
borg init --encryption=repokey-blake2 "$repo" >/dev/null 2>&1 && ok "init" || { bad "init"; exit 1; }
borg create "$repo::s1" "$data" >/dev/null 2>&1 && ok "first backup (s1)" || { bad "first backup"; exit 1; }

# 1. Does it mount at all, and is the content readable?
if out=$(borg mount "$repo" "$mnt" 2>&1); then
    ok "borg mount"
    if [ -n "$(ls "$mnt" 2>/dev/null)" ]; then
        ok "mounted: snapshots listed: $(ls "$mnt" | tr '\n' ' ')"
    else
        bad "mounted but empty"
    fi
    f=$(find "$mnt" -name a.txt 2>/dev/null | head -1)
    [ -n "$f" ] && [ "$(cat "$f")" = one ] && ok "a file reads back through the mount" || bad "file did not read back"
else
    bad "borg mount: $out"
    say ""
    say "Without a working mount M5 cannot rest on it. Stopping."
    exit 1
fi

# 2. With the mount ACTIVE, can another backup run? (the hourly timer would try exactly this)
echo two >"$data/b.txt"
say ""
say "-- a backup while the repository is mounted (lock wait 3 s):"
if out=$(borg create --lock-wait 3 "$repo::s2" "$data" 2>&1); then
    ok "borg create works while mounted"
else
    bad "borg create is BLOCKED by an active mount"
    say "   borg said: $(printf '%s' "$out" | tail -2 | tr '\n' ' ')"
fi

# 3. With the mount active, can the daemon still list (ListVersions/ListFolder use borg list)?
if out=$(borg list --lock-wait 3 "$repo" 2>&1); then
    ok "borg list works while mounted"
else
    bad "borg list is BLOCKED by an active mount"
    say "   borg said: $(printf '%s' "$out" | tail -2 | tr '\n' ' ')"
fi

# 4. After unmounting, back to normal?
if borg umount "$mnt" >/dev/null 2>&1; then
    ok "borg umount"
else
    fusermount3 -u "$mnt" >/dev/null 2>&1 && ok "fusermount3 -u (borg umount failed)" || bad "umount"
fi
echo three >"$data/c.txt"
borg create --lock-wait 3 "$repo::s3" "$data" >/dev/null 2>&1 && ok "borg create after umount" || bad "borg create after umount"

# 5. The other direction: a backup RUNNING, can a mount start? (user opens the backups mid-backup)
say ""
say "-- a mount while a backup is running (200 MB of random data):"
dd if=/dev/urandom of="$data/big.bin" bs=1M count=200 >/dev/null 2>&1
borg create --lock-wait 3 "$repo::s4" "$data" >/dev/null 2>&1 &
creator=$!
sleep 1
if out=$(borg mount --lock-wait 1 "$repo" "$mnt" 2>&1); then
    ok "borg mount works while a backup runs"
    borg umount "$mnt" >/dev/null 2>&1 || fusermount3 -u "$mnt" >/dev/null 2>&1 || true
else
    bad "borg mount is REFUSED while a backup runs"
    say "   borg said: $(printf '%s' "$out" | tail -2 | tr '\n' ' ')"
fi
wait "$creator" 2>/dev/null

say ""
say "== $pass passed, $fail failed =="
[ "$fail" -eq 0 ]
