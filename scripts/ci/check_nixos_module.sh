#!/bin/sh
# Checks what the NixOS module of Delta gave a system: the user units, and what a session finds in the profile.
# Usage: check_nixos_module.sh RESULT   (the output of scripts/ci/nixos-module-check.nix: its `units`, `profile`, `extra-init`)
set -eu

result=${1:?usage: check_nixos_module.sh RESULT}
units=$result/units
profile=$result/profile
failed=0

check() {
    description=$1
    shift
    if "$@" > /dev/null 2>&1; then
        echo "ok: $description"
    else
        echo "FAILED: $description" >&2
        failed=1
    fi
}

for unit in delta.service delta.timer delta-backup.service; do
    check "the user unit $unit exists" test -e "$units/$unit"
done
check "the daemon is a D-Bus service of the right name" grep -q '^BusName=io.github.sincorchetes.Delta.Service1$' "$units/delta.service"
check "the daemon is of type dbus" grep -q '^Type=dbus$' "$units/delta.service"
check "the timer is hourly" grep -q '^OnCalendar=hourly$' "$units/delta.timer"
check "the timer is started with the timers" test -e "$units/timers.target.wants/delta.timer"

check "the session bus can start the daemon" test -e "$profile/share/dbus-1/services/io.github.sincorchetes.Delta.Service1.service"
check "Files loads the extension" test -e "$profile/share/nautilus-python/extensions/delta_extension.py"
check "the manual is where Yelp looks" test -d "$profile/share/help/C/delta"
check "the translations are where the extension looks" test -e "$profile/share/locale/es/LC_MESSAGES/delta.mo"

# The schema is not in the profile (nixpkgs keeps it under share/gsettings-schemas/<name>/): the module adds that folder of the
# package to XDG_DATA_DIRS, which every session reads.
schemas=$(grep -o '/nix/store/[^[:space:]]*/share/gsettings-schemas/delta-[^[:space:]]*' "$result/extra-init" | head -n 1 || true)
check "the settings schema of Delta is added to XDG_DATA_DIRS" test -n "$schemas"
check "that schema is compiled" test -e "$schemas/glib-2.0/schemas/gschemas.compiled"

exit "$failed"
