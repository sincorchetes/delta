# Yelp looks for <datadir>/help/<language>/delta/*.page; C is the original (English).
foreach language : ['C', 'es']
  install_subdir(
    language,
    install_dir: join_paths(datadir, 'help', language, 'delta'),
    strip_directory: true,
    install_tag: 'doc',
  )
endforeach
