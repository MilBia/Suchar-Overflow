const { merge } = require('webpack-merge');
const common = require('./common.config.js');

// `npm run dev` (the `node` compose service): webpack-dev-server on :3000 serves the
// bundles and proxies everything else to Django, so a change to a template or a source
// file reloads the page. Django on :8000 keeps working: the bundles are also written to
// disk (static/webpack_bundles/) where its static handler finds them, and
// webpack-stats.json names them.
module.exports = merge(common, {
    mode: 'development',
    // Never an `eval*` devtool: the CSP has no 'unsafe-eval'.
    devtool: 'cheap-module-source-map',
    devServer: {
        host: '0.0.0.0',
        port: 3000,
        allowedHosts: 'all',
        hot: false,
        liveReload: true,
        // The dev server's gzip would buffer /achievements/stream/ (SSE) on its way through the proxy.
        compress: false,
        // The client's socket follows the page's own origin (port 0 = location.port), never a
        // fixed :3000: on :8000 a cross-origin socket would be a CSP `connect-src` violation.
        // There it just fails to connect (one retry) and gives up.
        client: {
            webSocketURL: 'auto://0.0.0.0:0/ws',
            reconnect: 1,
            overlay: { errors: true, warnings: false },
        },
        devMiddleware: { writeToDisk: true },
        watchFiles: { paths: ['suchar_overflow/templates/**/*.html'] },
        // Everything the dev server does not serve itself goes to Django. Host and Origin stay
        // localhost:3000 (changeOrigin off), so ALLOWED_HOSTS and the CSRF origin check see
        // the address the browser used.
        proxy: [
            {
                context: () => true,
                target: process.env.DJANGO_PROXY_TARGET || 'http://django:8000',
                changeOrigin: false,
                ws: false,
            },
        ],
    },
});
