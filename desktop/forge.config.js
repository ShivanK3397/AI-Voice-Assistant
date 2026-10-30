module.exports = {
  packagerConfig: { asar: true, executableName: 'Jarvis' },
  makers: [],
  plugins: [{
    name: '@electron-forge/plugin-vite',
    config: {
      build: [
        { entry: 'src/main.ts', config: 'vite.main.config.ts', target: 'main' },
        { entry: 'src/preload.ts', config: 'vite.preload.config.ts', target: 'preload' },
      ],
      renderer: [{ name: 'main_window', config: 'vite.renderer.config.ts' }],
    },
  }],
};
