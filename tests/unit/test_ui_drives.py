from delta.ui.drives import FOLDER_ON_DRIVE, Drive, removable_drives


class Root:
    def __init__(self, path):
        self._path = path

    def get_path(self):
        return self._path


class FakeDrive:
    def __init__(self, removable):
        self._removable = removable

    def is_removable(self):
        return self._removable


class FakeVolume:
    def __init__(self, drive):
        self._drive = drive

    def get_drive(self):
        return self._drive


class FakeMount:
    def __init__(self, name, path, *, eject=False, drive=None, shadowed=False, volume=True):
        self._name, self._path, self._eject, self._shadowed = name, path, eject, shadowed
        self._volume = FakeVolume(drive) if volume else None

    def get_name(self):
        return self._name

    def get_root(self):
        return Root(self._path) if self._path else None

    def get_volume(self):
        return self._volume

    def can_eject(self):
        return self._eject

    def is_shadowed(self):
        return self._shadowed


def test_a_usb_stick_is_offered():
    mounts = [FakeMount("BACKUPS", "/run/media/me/BACKUPS", eject=True)]
    assert removable_drives(mounts) == [Drive("BACKUPS", "/run/media/me/BACKUPS")]


def test_a_removable_drive_is_offered_even_if_it_cannot_be_ejected():
    mounts = [FakeMount("SD", "/run/media/me/SD", drive=FakeDrive(True))]
    assert [d.name for d in removable_drives(mounts)] == ["SD"]


def test_the_system_disk_is_never_offered():
    mounts = [
        FakeMount("root", "/", drive=FakeDrive(False)),
        FakeMount("home", "/home", volume=False),
    ]
    assert removable_drives(mounts) == []


def test_shadowed_mounts_and_mounts_without_a_path_are_skipped():
    mounts = [
        FakeMount("hidden", "/run/media/me/x", eject=True, shadowed=True),
        FakeMount("nopath", None, eject=True),
    ]
    assert removable_drives(mounts) == []


def test_backups_go_in_their_own_folder_on_the_drive():
    drive = Drive("BACKUPS", "/run/media/me/BACKUPS")
    assert drive.suggested_folder == f"/run/media/me/BACKUPS/{FOLDER_ON_DRIVE}"
