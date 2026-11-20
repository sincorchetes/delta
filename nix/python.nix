{ python3 }:

# The interpreter and the Python libraries (PyGObject, pycairo) of the nixpkgs the package is built with: like any other
# distribution, Delta uses what the packaging of its channel ships. The pins of uv.lock are for development only.
{
  python = python3;
  env = python3.withPackages (ps: [ ps.pygobject3 ]);
}
