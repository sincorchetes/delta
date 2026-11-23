{ pkgs, ... }:

{
  # System libraries and tooling only. Python dependencies are declared in
  # pyproject.toml (Poetry / PEP 621) and installed by uv into .venv — no
  # python3Packages from nixpkgs are used.
  packages = with pkgs; [
    meson
    ninja
    pkg-config
    gcc
    glib
    libffi
    cairo
    dbus
    libsecret
    gnome-keyring
    borgbackup
    appstream
    desktop-file-utils # desktop-file-validate: the one from the user profile needs another glibc than the devenv's libraries
    flatpak-builder # builds flatpak/*.yaml
    flatpak # enough for --user installs; to run it integrated in the session use services.flatpak.enable on NixOS
    gvfs
    shared-mime-info # the MIME database: Gio.content_type_guess needs it to know that note.txt is text (NixOS has it; the CI does not)
    gtk4
    libadwaita
    gst_all_1.gstreamer
    gst_all_1.gst-plugins-base
    gst_all_1.gst-plugins-good
    gst_all_1.gst-plugins-bad
    gst_all_1.gst-libav
    gobject-introspection
    nautilus
    nautilus-python
    fuse3
    xvfb-run # a display for the GTK widget tests where there is none (CI)
    bun # builds the documentation site (website/)
    patchelf
    ruff # from nixpkgs: the PyPI wheel is a generic binary that does not run on NixOS
    pyright # type checking (pyproject.toml, [tool.pyright]); from nixpkgs for the same reason: the PyPI wheel downloads a Node binary
  ];

  languages.python = {
    enable = true;
    package = pkgs.python313;
    uv.enable = true;
    poetry = {
      enable = true;
      install.enable = false; # uv is the installer; poetry only defines/builds
    };
  };

  enterShell = ''
    export PATH="$DEVENV_ROOT/.devenv/state/venv/bin:$PATH"
    # Where GLib looks for the MIME database: devenv does not add the share/ of its packages by itself.
    export XDG_DATA_DIRS="${pkgs.shared-mime-info}/share''${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"
  '';

  scripts.sync.exec = ''
    sh scripts/sync-venv.sh
  '';

  scripts.build.exec = ''
    if [ -d build ]; then
      meson setup build --reconfigure
    else
      meson setup build
    fi
    meson compile -C build
  '';

  scripts.test.exec = ''
    sh scripts/sync-venv.sh
    uv run pytest "$@"
  '';

  # Tests with coverage (100 % required). The GTK widget tests need a display: the session's own
  # when there is one, a virtual one otherwise. Pass pytest options through, e.g. `cov -x`.
  # Not called `coverage`: the venv's own coverage.py executable would shadow it.
  scripts.cov.exec = ''
    sh scripts/sync-venv.sh
    if [ -n "$WAYLAND_DISPLAY$DISPLAY" ]; then
      uv run pytest --cov --cov-report=term-missing "$@"
    else
      xvfb-run -a uv run pytest --cov --cov-report=term-missing "$@"
    fi
  '';

  # Builds the Flatpak and installs it for your user (then: flatpak run io.github.sincorchetes.Delta).
  # To run the result integrated in the session (portals, background start): services.flatpak.enable on NixOS.
  scripts.flatpak-build.exec = ''
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    # --disable-rofiles-fuse: on NixOS the fusermount of the Nix store is not setuid, so rofiles-fuse cannot mount.
    flatpak-builder --user --install --install-deps-from=flathub --force-clean --disable-rofiles-fuse \
      build-flatpak flatpak/io.github.sincorchetes.Delta.yaml "$@"
  '';

  scripts.update.exec = ''
    git add .  # first: a flake only sees the files git knows, so a new one is not in the build otherwise
    nix flake lock
    nix build '.#default'
    git commit -m "Add code"
    git push
    cd ~/Documents/system/nixos-flake-hardware-profiles/
    nix flake update delta
    run0 nixos-rebuild switch "$@" \
    --flake "$HOME/Documents/system/nixos-flake-hardware-profiles#$(hostname)" \
    --override-input secrets "path:$HOME/Documents/system/nixos-flake-hardware-profiles/secrets"
    systemctl --user restart delta
    nautilus -q
    
  '';

  enterTest = ''
    sh scripts/sync-venv.sh
    uv run pytest -q
  '';
}
