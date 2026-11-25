project(
  'delta',
  version: '0.4.0',
  meson_version: '>= 1.0',
  license: 'GPL-3.0-or-later',
)

python = import('python')
gnome = import('gnome')
i18n = import('i18n')

python_inst = python.find_installation('python3', required: true)

prefix = get_option('prefix')
datadir = join_paths(prefix, get_option('datadir'))
bindir = join_paths(prefix, get_option('bindir'))
libexecdir = join_paths(prefix, get_option('libexecdir'))
localedir = join_paths(prefix, get_option('localedir'))
userunitdir = join_paths(prefix, 'lib', 'systemd', 'user')
dbus_services_dir = join_paths(datadir, 'dbus-1', 'services')
gschema_dir = join_paths(datadir, 'glib-2.0', 'schemas')

subdir('data')
subdir('src')
subdir('po')
subdir('help')

# Only where the tool exists: a package of a distribution never runs it (its own triggers refresh the cache).
icon_cache_tool = find_program('gtk4-update-icon-cache', 'gtk-update-icon-cache', required: false)
gnome.post_install(glib_compile_schemas: true, gtk_update_icon_cache: icon_cache_tool.found())
