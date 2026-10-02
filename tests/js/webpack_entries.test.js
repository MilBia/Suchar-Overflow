// @vitest-environment node
/**
 * Guard for the module sharing between webpack entries (#468).
 *
 * A page entry (`leaderboard`, `voting`, ...) that imports `easter_eggs.js`, `toast.js` or `csrf.js`
 * must get the instance the global `project` entry already evaluated. Without `dependOn: 'project'`
 * (and the single runtime) webpack copies small shared modules into every entry that imports them:
 * two `easterEggs` objects, two dedupe Sets, two teardown registries — silent, and invisible to the
 * per-module Vitest suites. This builds the production config into a temp dir (stats file and all
 * other plugins' side effects aside) and counts the chunks each shared module landed in.
 */
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import webpack from 'webpack';
import prodConfig from '../../webpack/prod.config.js';

const SHARED_MODULES = ['features/easter_eggs.js', 'toast.js', 'csrf.js', 'timezone.js'];

function build() {
    const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'suchar-webpack-'));
    const config = {
        ...prodConfig,
        output: { ...prodConfig.output, path: outDir },
        // The stats file belongs to the real build; keep this one out of the repo root.
        plugins: prodConfig.plugins.filter((plugin) => plugin.constructor.name !== 'BundleTrackerPlugin'),
        devtool: false,
        cache: false,
        // Concatenated modules are listed as one `a.js + N modules` entry; keep them separate to count them.
        optimization: { ...prodConfig.optimization, concatenateModules: false, minimize: false },
    };
    return new Promise((resolve, reject) => {
        webpack(config, (error, stats) => {
            // The temp dir goes whether the build succeeded, failed or threw while reading the stats.
            const cleanup = () => fs.rmSync(outDir, { recursive: true, force: true });
            if (error) {
                cleanup();
                return reject(error);
            }
            if (stats.hasErrors()) {
                cleanup();
                return reject(new Error(stats.toString({ all: false, errors: true })));
            }
            const json = stats.toJson({
                all: false,
                chunks: true,
                chunkModules: true,
                chunkModulesSpace: Infinity,
                nestedModules: true,
                // Without these the chunk's modules are folded into a "dependent modules" group.
                dependentModules: true,
                entrypoints: true,
            });
            json.licenses = fs.readFileSync(path.join(outDir, 'licenses.txt'), 'utf8');
            cleanup();
            return resolve(json);
        });
    });
}

let stats;

beforeAll(async () => {
    stats = await build();
}, 120_000);

describe('shared modules across entries', () => {
    it.each(SHARED_MODULES)('%s is bundled into exactly one chunk', (suffix) => {
        const holders = stats.chunks.filter((chunk) =>
            (chunk.modules || []).some((mod) =>
                (mod.name || '').replace(/^\.\//, '').endsWith(`webpack/src/js/${suffix}`),
            ),
        );
        expect(holders.map((chunk) => chunk.names)).toHaveLength(1);
    });

    it('the global entry imports timezone first, then the site script, then the easter eggs, in order', () => {
        const source = fs.readFileSync(path.resolve(__dirname, '../../webpack/src/js/project.js'), 'utf8');
        const imports = [...source.matchAll(/^import '([^']+)';$/gm)].map((match) => match[1]);
        expect(imports.filter((file) => file.endsWith('.js'))).toEqual([
            './timezone.js',
            './app.js',
            './features/easter_eggs.js',
            './features/konami.js',
            './features/badumtss.js',
            './features/logo_spin.js',
            './features/console_egg.js',
            './features/tumbleweed.js',
            './features/theme_spam.js',
            './features/archeolog.js',
            './features/publika_rozgrzana.js',
        ]);
    });
});

describe('third-party licences (#251)', () => {
    // flatpickr's ES build carries no licence comment for a minifier to keep, so the notice has to be
    // written out from the package itself — it must reach an artifact the site serves.
    it.each(['flatpickr', 'chart.js'])('licenses.txt carries the MIT text of %s', (name) => {
        const section = stats.licenses.split('\n' + '-'.repeat(72) + '\n').find((part) => part.includes(`${name} `));
        expect(section).toBeDefined();
        expect(section).toMatch(/MIT/);
        expect(section).toMatch(/Permission is hereby granted/);
    });
});
