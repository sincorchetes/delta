{
  description = "Delta: GNOME integrated, BorgBackup powered file time travel";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        delta = pkgs.callPackage ./nix/package.nix { };
        default = delta;
      });

      homeManagerModules.default = import ./nix/home-manager.nix self;
      nixosModules.default = import ./nix/nixos.nix self;
    };
}
