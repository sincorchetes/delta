- **The cache of Flatpak apps is no longer backed up.** Only `~/.cache` was skipped, but a Flatpak app keeps its cache in
  `~/.var/app/<id>/cache`, which with the whole home folder as the source filled the backups with what any app makes again. Its data
  (`~/.var/app/<id>/data`, `config`) is still copied.
