#!/bin/sh
# What the Flatpak does once it is installed, which a build and an attached bundle never show: BorgBackup (built offline) runs
# in the sandbox, the application is the version of this tree, the daemon starts and owns its name on the bus, and the window
# opens and stays open with no traceback and no GLib critical.
#
# It does not make a backup: the passphrase goes to the keyring through a portal that a CI runner does not have.
#
#   flatpak_smoke.sh BUNDLE      installs the bundle for the user first (delta.flatpak, from `flatpak build-bundle`)
#   flatpak_smoke.sh --installed uses what is installed already (after `flatpak-build` in devenv)
#
# It needs dbus-run-session and xvfb-run (it runs itself under both, so that the daemon and the window have a bus and a display).
set -eu

app=io.github.sincorchetes.Delta
bus_name=io.github.sincorchetes.Delta.Service1
here=$(cd "$(dirname "$0")" && pwd)
tree=$(cd "$here/../.." && pwd)

if [ "${DELTA_FLATPAK_SMOKE_INSIDE:-}" != 1 ]; then
    DELTA_FLATPAK_SMOKE_INSIDE=1 exec dbus-run-session -- xvfb-run -a sh "$0" "$@"
fi

work=$(mktemp -d)
trap 'flatpak kill "$app" 2> /dev/null || true; rm -rf "$work"' EXIT

step() { printf '\n== %s\n' "$*"; }
fail() {
    echo "flatpak_smoke.sh: $*" >&2
    exit 1
}
log_tail() { tail -n 15 "$1" 2> /dev/null | sed 's/^/    /' >&2 || true; }

case ${1:-} in
    --installed) ;;
    '') fail "usage: flatpak_smoke.sh BUNDLE | --installed" ;;
    *)
        step "the bundle installs"
        flatpak install --user --noninteractive --assumeyes "$1" || fail "the bundle does not install"
        ;;
esac

step "BorgBackup, built offline, runs in the sandbox"
flatpak run --command=borg "$app" --version || fail "borg does not run inside the Flatpak"

step "the application is the version of this tree"
expected=$(sed -n "s/^ *version: *'\([^']*\)'.*/\1/p" "$tree/meson.build" | head -1)
found=$(flatpak run --command=python3 "$app" -c 'import delta; print(delta.__version__)') || fail "delta cannot be imported inside the Flatpak"
[ "$found" = "$expected" ] || fail "the Flatpak has Delta $found and this tree says $expected"
echo "Delta $found"

step "the daemon starts and owns its name on the bus"
flatpak run --command=delta-daemon "$app" > "$work/daemon.log" 2>&1 &
seconds=0
until [ "$(gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.NameHasOwner "$bus_name" 2> /dev/null)" = "(true,)" ]; do
    seconds=$((seconds + 1))
    if [ "$seconds" -gt 40 ]; then
        log_tail "$work/daemon.log"
        fail "the daemon does not own $bus_name after 40 seconds"
    fi
    sleep 1
done
status=$(gdbus call --session --dest "$bus_name" --object-path /io/github/sincorchetes/Delta/Service1 \
    --method org.freedesktop.DBus.Properties.Get "$bus_name" Status) || fail "the daemon does not answer"
echo "Status: $status"
case $status in *idle* | *unavailable*) ;; *) fail "unexpected Status $status" ;; esac

step "the window opens and stays open"
printf 'a file for the window to look at\n' > "$HOME/delta-flatpak-smoke.txt"
flatpak run --env=GSK_RENDERER=cairo "$app" --versions "$HOME/delta-flatpak-smoke.txt" > "$work/window.log" 2>&1 &
window=$!
sleep 12
kill -0 "$window" 2> /dev/null || {
    log_tail "$work/window.log"
    rm -f "$HOME/delta-flatpak-smoke.txt"
    fail "the window exited"
}
rm -f "$HOME/delta-flatpak-smoke.txt"
# GTK's own critical of the software renderer on a virtual display (the same one that package_smoke.py knows)
if grep -E "Traceback|-CRITICAL" "$work/window.log" | grep -v "gdk_cairo_format_for_content" > "$work/problems.log"; then
    cat "$work/problems.log" >&2
    fail "the window printed a problem"
fi

printf '\nflatpak_smoke.sh: ok\n'
