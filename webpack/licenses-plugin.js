const fs = require('fs');
const path = require('path');

// webpack reports `module.resource` with forward slashes on every OS, so match on those.
const NODE_MODULES = '/node_modules/';
const LICENSE_FILES = ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'license', 'license.md', 'LICENCE', 'LICENCE.md'];

// `license` is a string today, but older packages use `{type, url}` or a `licenses` array.
function licenseId(pkg) {
    if (typeof pkg.license === 'string') return pkg.license;
    if (pkg.license && typeof pkg.license.type === 'string') return pkg.license.type;
    if (Array.isArray(pkg.licenses)) {
        return pkg.licenses
            .map((entry) => (typeof entry === 'string' ? entry : entry.type))
            .filter(Boolean)
            .join(', ');
    }
    return '';
}

/**
 * Writes `licenses.txt` next to the bundles: name, version and licence text of every npm package that
 * ended up in a bundle (#468, #251).
 *
 * Minifiers keep a licence only if it sits in a `/*!` or `@license` comment, and an ES build of a
 * package (flatpickr's `module` field, for one) often has none — so the MIT text of a bundled library
 * would otherwise appear in nothing the site serves. This does not depend on how a package comments
 * its source. The file is served at /static/webpack_bundles/licenses.txt.
 */
class LicensesPlugin {
    constructor({ filename = 'licenses.txt' } = {}) {
        this.filename = filename;
    }

    apply(compiler) {
        const { Compilation, sources } = compiler.webpack;
        compiler.hooks.thisCompilation.tap('LicensesPlugin', (compilation) => {
            compilation.hooks.processAssets.tap(
                { name: 'LicensesPlugin', stage: Compilation.PROCESS_ASSETS_STAGE_ADDITIONAL },
                () => {
                    const packages = new Map();
                    for (const module of compilation.modules) {
                        const resource = (module.resource || '').replace(/\\/g, '/');
                        const at = resource.lastIndexOf(NODE_MODULES);
                        if (at === -1) continue;
                        const parts = resource.slice(at + NODE_MODULES.length).split('/');
                        const name = parts[0].startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0];
                        const dir = resource.slice(0, at + NODE_MODULES.length) + name;
                        packages.set(name, dir);
                    }
                    const sections = [...packages.entries()]
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([name, dir]) => {
                            const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
                            const version = pkg.version || '?';
                            const license = licenseId(pkg);
                            const file = LICENSE_FILES.find((candidate) => fs.existsSync(path.join(dir, candidate)));
                            const text = file
                                ? fs.readFileSync(path.join(dir, file), 'utf8').trim()
                                : '(no licence file in the package)';
                            return `${name} ${version} — ${license}\n\n${text}\n`;
                        });
                    const body = `Third-party code bundled into the site's JavaScript and CSS.\n\n${sections.join(`\n${'-'.repeat(72)}\n\n`)}`;
                    compilation.emitAsset(this.filename, new sources.RawSource(body));
                },
            );
        });
    }
}

module.exports = LicensesPlugin;
