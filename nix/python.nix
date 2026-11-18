{ python313, fetchurl }:

# Python libraries pinned to the exact sdists in uv.lock (not nixpkgs' versions).
# Keep these in sync with uv.lock when it changes. The interpreter is pinned to 3.13 (as in
# devenv.nix): PyGObject 3.58.1 cannot convert callbacks to closures under Python 3.14.
let
  python = python313.override {
    self = python;
    packageOverrides = _final: prev: {
      pycairo = prev.pycairo.overridePythonAttrs (_: {
        version = "1.29.2";
        src = fetchurl {
          url = "https://files.pythonhosted.org/packages/bb/5e/19ab2572981a996ce96b853a189d2dcced40506b67d9555a7568457abcf2/pycairo-1.29.2.tar.gz";
          sha256 = "3e69fff74fe64f5ba2dfa31f67c6bdf26413342574047437d2ac520d35e9a489";
        };
      });

      pygobject3 = prev.pygobject3.overridePythonAttrs (_: {
        version = "3.58.1";
        src = fetchurl {
          url = "https://files.pythonhosted.org/packages/65/1e/d590f82e14db75945b03f6b63e0f19662e0340babd8f574fdb1bb5a015e2/pygobject-3.58.1.tar.gz";
          sha256 = "4c80598ade17fbaa7798e01a25d0bf29ce109740786026a074c5c62bb3e79d23";
        };
      });
    };
  };
in
{
  inherit python;
  env = python.withPackages (ps: [ ps.pygobject3 ]);
}
