// Third-party runtimes for the live preview, loaded on demand by worker.js.
//
// Versions are pinned here and in package.json (devDependencies, so a local
// `npm ci` gives the same files for offline development and tests). The
// `deps.test.js` check keeps the two in sync.
//
// Production loads from jsDelivr's npm mirror. Opening the editor with
// `?local-deps` serves them from ./node_modules instead (after `npm ci`).

export const PYODIDE_VERSION = '314.0.7';
export const VEROVIO_VERSION = '6.3.0';

const CDN = 'https://cdn.jsdelivr.net/npm/';

/**
 * Base URLs (with trailing slash) for the Pyodide and Verovio distributions.
 * @param {{ local?: boolean, baseUrl?: string }} [opts]
 */
export function depUrls({ local = false, baseUrl = import.meta.url } = {}) {
  if (local) {
    const nm = new URL('node_modules/', baseUrl).href;
    return { pyodide: `${nm}pyodide/`, verovio: `${nm}verovio/dist/` };
  }
  return {
    pyodide: `${CDN}pyodide@${PYODIDE_VERSION}/`,
    verovio: `${CDN}verovio@${VEROVIO_VERSION}/dist/`,
  };
}
