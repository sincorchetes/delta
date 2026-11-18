self:
{ config, lib, pkgs, ... }:

let
  cfg = config.services.delta;
  bus = "io.github.sincorchetes.Delta.Service1";
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
    # The right-click menu of Files needs nautilus-python, and nixpkgs does not install it with Files.
    environment.systemPackages = [ cfg.package pkgs.nautilus-python ];

    # The session bus starts the daemon from share/dbus-1/services of these packages.
    services.dbus.packages = [ cfg.package ];

    # What the extension (it runs inside Files) and the F1 help look for in XDG_DATA_DIRS.
    environment.pathsToLink = [
      "/share/nautilus-python/extensions"
      "/share/help"
      "/share/locale"
    ];

    # nixpkgs keeps the settings schema under share/gsettings-schemas/<name>/, which is not in XDG_DATA_DIRS by itself
    # (the GNOME module adds it only for its own sessionPath). The extension reads the settings from inside Files.
    environment.extraInit = ''
      export XDG_DATA_DIRS=$XDG_DATA_DIRS''${XDG_DATA_DIRS:+:}${cfg.package}/share/gsettings-schemas/${cfg.package.name}
    '';

    # NixOS builds /etc/systemd/user only from these options, so the units of the package
    # (share/systemd/user) would never be seen: they are declared here, the same as data/systemd/.
    systemd.user.services.delta = {
      description = "Delta backup daemon";
      serviceConfig = {
        Type = "dbus";
        BusName = bus;
        ExecStart = "${cfg.package}/libexec/delta-daemon";
      };
    };

    systemd.user.services.delta-backup = {
      description = "Delta scheduled backup trigger";
      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.concatStringsSep " " [
          "${lib.getBin pkgs.glib}/bin/gdbus call --session"
          "--dest ${bus}"
          "--object-path /io/github/sincorchetes/Delta/Service1"
          "--method ${bus}.CreateBackup"
        ];
      };
    };

    systemd.user.timers.delta = {
      description = "Delta scheduled backups";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "hourly";
        Persistent = true;
        Unit = "delta-backup.service";
      };
    };
  };
}
