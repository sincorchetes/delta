self:
{ config, lib, pkgs, ... }:

let
  cfg = config.services.delta;
  share = "${cfg.package}/share";
in
{
  options.services.delta = {
    enable = lib.mkEnableOption "Delta, GNOME file time travel on BorgBackup";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "delta.packages.\${system}.default";
      description = "The Delta package to install.";
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];

    # systemd and the session bus always search $XDG_DATA_HOME, so these links
    # do not depend on the Nix profile being in XDG_DATA_DIRS.
    xdg.dataFile = {
      "systemd/user" = {
        source = "${share}/systemd/user";
        recursive = true;
      };
      "dbus-1/services" = {
        source = "${share}/dbus-1/services";
        recursive = true;
      };
      # The app (visible) and the daemon (hidden; notifications are attributed to it).
      "applications/io.github.sincorchetes.Delta.desktop".source = "${share}/applications/io.github.sincorchetes.Delta.desktop";
      "applications/io.github.sincorchetes.Delta.Daemon.desktop".source = "${share}/applications/io.github.sincorchetes.Delta.Daemon.desktop";
      # Hidden entry the Nautilus extension launches to open the version browser of a file.
      "applications/io.github.sincorchetes.Delta.Versions.desktop".source = "${share}/applications/io.github.sincorchetes.Delta.Versions.desktop";

      # The Nautilus extension is NOT linked here: the package in home.packages already exposes it
      # under share/nautilus-python/extensions, and nautilus-python scans both $XDG_DATA_HOME and
      # $XDG_DATA_DIRS, so a second link made the menu entry appear twice.
      # nautilus-python itself must be installed system-wide.

      # The manual (Mallard pages): Yelp searches $XDG_DATA_HOME, not the Nix profile, so F1 finds it here.
      "help" = {
        source = "${share}/help";
        recursive = true;
      };

      # The extension runs inside Nautilus, so it finds Delta's translations through XDG_DATA_HOME.
      "locale" = {
        source = "${share}/locale";
        recursive = true;
      };

      # nixpkgs keeps schemas under share/gsettings-schemas/<name>/, which the
      # `gsettings` CLI and other apps do not search; $XDG_DATA_HOME is searched.
      # If you already keep other schemas there, this link will conflict visibly.
      "glib-2.0/schemas" = {
        source = "${share}/gsettings-schemas/${cfg.package.name}/glib-2.0/schemas";
        recursive = true;
      };
    };
  };
}
