# A minimal NixOS system with the module of Delta, to build its user units and its profile and check them
# (scripts/ci/check_nixos_module.sh). Two ways of using the module, as a person would:
#   withFlake = true   the flake of this repository, as `delta.nixosModules.default`;
#   withFlake = false  the file imported by path from a plain configuration.nix, with no flake.
#
#   nix build --impure --expr 'import ./scripts/ci/nixos-module-check.nix { withFlake = true; }'
{ withFlake }:

let
  flake = builtins.getFlake (toString ../..);
  nixpkgs = flake.inputs.nixpkgs;
  system = "x86_64-linux";

  host = { ... }: {
    services.delta.enable = true;
    fileSystems."/" = { device = "/dev/vda"; fsType = "ext4"; };
    boot.loader.grub.enable = false;
    system.stateVersion = "26.05";
  };

  nixos =
    if withFlake then
      nixpkgs.lib.nixosSystem { inherit system; modules = [ flake.nixosModules.default host ]; }
    else
      import (nixpkgs + "/nixos") { inherit system; configuration = { imports = [ ../../nix/nixos.nix host ]; }; };
in
nixpkgs.legacyPackages.${system}.linkFarm "delta-nixos-module" [
  { name = "units"; path = nixos.config.environment.etc."systemd/user".source; }
  { name = "profile"; path = nixos.config.system.path; }
  { name = "extra-init"; path = nixpkgs.legacyPackages.${system}.writeText "extra-init" nixos.config.environment.extraInit; }
]
