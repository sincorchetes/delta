install_data(
  'io.github.sincorchetes.Delta.gschema.xml',
  install_dir: gschema_dir,
)

libexec_conf = configuration_data()
libexec_conf.set('libexecdir', libexecdir)
libexec_conf.set('localedir', localedir)
libexec_conf.set('bindir', bindir)
# Where systemd runs the daemon, D-Bus asks it to; without systemd units (a Flatpak) D-Bus starts it itself.
libexec_conf.set('systemd_service', get_option('systemd_units') ? 'SystemdService=delta.service' : '')

configure_file(
  input: 'io.github.sincorchetes.Delta.Service1.service.in',
  output: 'io.github.sincorchetes.Delta.Service1.service',
  configuration: libexec_conf,
  install_dir: dbus_services_dir,
)

if get_option('systemd_units')
  configure_file(
    input: 'systemd/delta.service.in',
    output: 'delta.service',
    configuration: libexec_conf,
    install_dir: userunitdir,
  )
endif

foreach desktop : ['io.github.sincorchetes.Delta.Daemon', 'io.github.sincorchetes.Delta.Versions']
  configure_file(
    input: desktop + '.desktop.in',
    output: desktop + '.desktop',
    configuration: libexec_conf,
    install_dir: join_paths(datadir, 'applications'),
  )
endforeach

# The application's own entry is translated: the paths are filled in first, then the texts.
po_dir = join_paths(meson.project_source_root(), 'po')
app_desktop = configure_file(
  input: 'io.github.sincorchetes.Delta.desktop.in',
  output: 'io.github.sincorchetes.Delta.desktop.in',
  configuration: libexec_conf,
)
app_desktop_file = i18n.merge_file(
  input: app_desktop,
  output: 'io.github.sincorchetes.Delta.desktop',
  type: 'desktop',
  po_dir: po_dir,
  install: true,
  install_dir: join_paths(datadir, 'applications'),
)
metainfo_file = i18n.merge_file(
  input: 'io.github.sincorchetes.Delta.metainfo.xml.in',
  output: 'io.github.sincorchetes.Delta.metainfo.xml',
  type: 'xml',
  po_dir: po_dir,
  install: true,
  install_dir: join_paths(datadir, 'metainfo'),
)

install_data(
  'icons/hicolor/scalable/apps/io.github.sincorchetes.Delta.svg',
  install_dir: join_paths(datadir, 'icons', 'hicolor', 'scalable', 'apps'),
)
install_data(
  'icons/hicolor/symbolic/apps/io.github.sincorchetes.Delta-symbolic.svg',
  install_dir: join_paths(datadir, 'icons', 'hicolor', 'symbolic', 'apps'),
)

# Checks that only run where the tools exist.
appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test('validate the AppStream metadata', appstreamcli, args: ['validate', '--no-net', metainfo_file])
endif
desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test('validate the desktop entry', desktop_file_validate, args: [app_desktop_file])
endif

if get_option('systemd_units')
  gdbus_conf = configuration_data()
  gdbus_conf.set('gdbus', find_program('gdbus').full_path())

  configure_file(
    input: 'systemd/delta-backup.service.in',
    output: 'delta-backup.service',
    configuration: gdbus_conf,
    install_dir: userunitdir,
  )

  install_data('systemd/delta.timer', install_dir: userunitdir)
endif
