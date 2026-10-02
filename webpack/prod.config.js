const { merge } = require('webpack-merge');
const CssMinimizerPlugin = require('css-minimizer-webpack-plugin');
const common = require('./common.config.js');

module.exports = merge(common, {
    mode: 'production',
    // A build that cannot finish must not leave half a bundle for `collectstatic` to pick up.
    bail: true,
    // Real .map files next to the bundles. collectstatic's manifest storage hard-fails on a
    // `sourceMappingURL` that points at a missing file (#249), so a map is either emitted or
    // not referenced - never dangling.
    devtool: 'source-map',
    optimization: {
        minimizer: ['...', new CssMinimizerPlugin()],
    },
});
