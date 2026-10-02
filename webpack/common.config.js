const path = require('path');
const BundleTracker = require('webpack-bundle-tracker');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

const ROOT = path.resolve(__dirname, '..');

// Sources live outside suchar_overflow/static/ on purpose: collectstatic copies
// everything under STATICFILES_DIRS, and the sources must not ship next to the bundles.
module.exports = {
    context: ROOT,
    target: 'web',
    entry: {
        project: path.resolve(__dirname, 'src/js/project.js'),
    },
    output: {
        path: path.resolve(ROOT, 'suchar_overflow/static/webpack_bundles/'),
        publicPath: '/static/webpack_bundles/',
        // `.<12 hex>.<ext>` is the shape nginx matches for `Cache-Control: immutable`
        // (compose/production/nginx/default.conf), so keep the dot and the 12 digits.
        filename: 'js/[name].[contenthash].js',
        chunkFilename: 'js/[name].[contenthash].js',
        assetModuleFilename: 'assets/[name].[contenthash][ext]',
        hashDigestLength: 12,
        clean: true,
    },
    optimization: {
        // One runtime shared by every entry, so a page that loads two entries (the global
        // `project` plus a page script) never instantiates a module twice. The loader drops
        // the chunks a second `render_bundle` call would repeat (SKIP_COMMON_CHUNKS).
        runtimeChunk: 'single',
        splitChunks: { chunks: 'all' },
    },
    plugins: [
        new MiniCssExtractPlugin({
            filename: 'css/[name].[contenthash].css',
            chunkFilename: 'css/[name].[contenthash].css',
        }),
        // django-webpack-loader reads this file to turn `{% render_bundle 'project' %}`
        // into <script>/<link> tags. Gitignored, written by every build.
        new BundleTracker({
            path: ROOT,
            filename: 'webpack-stats.json',
        }),
    ],
    module: {
        rules: [
            {
                test: /\.js$/,
                exclude: /node_modules/,
                use: 'babel-loader',
            },
            {
                test: /\.(s?css)$/,
                use: [
                    MiniCssExtractPlugin.loader,
                    { loader: 'css-loader', options: { importLoaders: 2 } },
                    {
                        loader: 'postcss-loader',
                        options: { postcssOptions: { config: path.resolve(__dirname, 'postcss.config.js') } },
                    },
                    'sass-loader',
                ],
            },
            {
                // Fonts, images and audio referenced from url() in the stylesheets.
                test: /\.(woff2?|ttf|otf|eot|svg|png|jpe?g|gif|webp|avif|ico)$/,
                type: 'asset/resource',
            },
        ],
    },
    resolve: {
        extensions: ['.js', '.scss'],
    },
};
