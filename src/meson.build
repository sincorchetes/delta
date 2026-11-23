# The names are paths below `delta/`: `__pycache__` alone would leave out only the first one, and a working copy that has run
# the tests would install the bytecode of every subpackage (compiled by another Python, and of modules that no longer exist).
install_subdir(
  'delta',
  install_dir: python_inst.get_install_dir(),
  exclude_directories: [
    '__pycache__',
    'application/__pycache__',
    'daemon/__pycache__',
    'domain/__pycache__',
    'infrastructure/__pycache__',
    'ui/__pycache__',
  ],
)

install_data(
  'delta-daemon',
  install_dir: libexecdir,
  install_mode: 'rwxr-xr-x',
)

if get_option('nautilus_extension')
  install_data(
    'nautilus/delta_extension.py',
    install_dir: join_paths(datadir, 'nautilus-python', 'extensions'),
  )
endif

install_data(
  'delta-ui',
  install_dir: bindir,
  install_mode: 'rwxr-xr-x',
)
