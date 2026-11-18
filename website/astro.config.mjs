import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// Static output only: GitHub Pages serves plain files, so there is no server and no adapter.
export default defineConfig({
  site: 'https://delta.sincorchetes.tech',
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'Delta',
      description: 'File time travel for GNOME, backed by BorgBackup.',
      logo: { src: './src/assets/logo.svg', alt: '' },
      favicon: '/favicon.svg',
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/sincorchetes/delta' }],
      editLink: { baseUrl: 'https://github.com/sincorchetes/delta/edit/main/website/' },
      customCss: ['./src/styles/gnome.css'],
      defaultLocale: 'root',
      locales: {
        root: { label: 'English', lang: 'en-US' },
        es: { label: 'Español', lang: 'es-ES' },
      },
      sidebar: [
        {
          label: 'Start here',
          translations: { 'es-ES': 'Primeros pasos' },
          items: ['install', 'first-backup'],
        },
        {
          label: 'Using Delta',
          translations: { 'es-ES': 'Usar Delta' },
          items: ['status', 'preferences', 'restore', 'history'],
        },
        {
          label: 'Keeping it safe',
          translations: { 'es-ES': 'Mantenerlo a salvo' },
          items: ['recovery-key', 'troubleshooting'],
        },
        {
          label: 'Background',
          translations: { 'es-ES': 'Más información' },
          items: ['how-it-works', 'technical'],
        },
      ],
    }),
  ],
});
