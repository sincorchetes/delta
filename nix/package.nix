{
  lib,
  stdenv,
  callPackage,
  meson,
  ninja,
  pkg-config,
  gettext,
  glib,
  libsecret,
  gtk4,
  libadwaita,
  adwaita-icon-theme,
  gst_all_1,
  gobject-introspection,
  wrapGAppsHook4,
  borgbackup,
}:

let
  py = callPackage ./python.nix { };
  # The decoders of GTK's media backend (the player in the version window).
  gstPlugins = with gst_all_1; [
    gstreamer
    gst-plugins-base
    gst-plugins-good
    gst-plugins-bad
    gst-libav
  ];
in
stdenv.mkDerivation {
  pname = "delta";
  version = "0.1.2";

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../meson.build
      ../meson_options.txt
      ../data
      ../help
      ../po
      ../src
    ];
  };

  nativeBuildInputs = [
    py.env
    meson
    ninja
    pkg-config
    gettext
    glib
    (lib.getBin glib)
    gobject-introspection
    wrapGAppsHook4
  ];

  # Typelibs (GLib, Gio, GLibUnix, Secret, Gtk, Adw) reach the wrappers through
  # GI_TYPELIB_PATH: the daemon needs the first four, the app all of them.
  buildInputs = [
    glib
    libsecret
    gtk4
    libadwaita
  ] ++ gstPlugins;

  # The automatic pass looks for interpreters among buildInputs, but the Python
  # env is a build tool: point the daemon's shebang at it before wrapping.
  postInstall = ''
    patchShebangs --build $out/libexec/delta-daemon $out/bin/delta-ui
  '';

  # The daemon (libexec) and the app (bin) are wrapped by the hook; they need their own
  # Python package, GSettings schemas and borg at runtime.
  preFixup = ''
    gappsWrapperArgs+=(
      --prefix PYTHONPATH : "$out/${py.python.sitePackages}"
      --prefix XDG_DATA_DIRS : "$out/share"
      --suffix XDG_DATA_DIRS : "${adwaita-icon-theme}/share"
      --set-default DELTA_LOCALEDIR "$out/share/locale"
      --prefix PATH : "${lib.makeBinPath [ borgbackup ]}"
      # SET, never prefix: a GStreamer of another version in the user's own environment
      # (NixOS exports the system's) would load beside ours and abort decodebin3 on an .mp3.
      --set GST_PLUGIN_SYSTEM_PATH_1_0 "${lib.makeSearchPathOutput "out" "lib/gstreamer-1.0" gstPlugins}"
      --unset GST_PLUGIN_PATH_1_0
    )
  '';

  # Covered by the project's own pytest/CI and scripts/smoke_session.py.
  doCheck = false;

  meta = {
    description = "GNOME integrated, BorgBackup powered file time travel";
    license = lib.licenses.gpl3Plus;
    platforms = lib.platforms.linux;
  };
}
