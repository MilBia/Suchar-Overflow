// Global entry (#466). Still empty on purpose: until #468 moves the scripts here the
// classic `{% compress js %}` block in base.html keeps doing the work. The marker lets
// the E2E suite and a curious human check that the bundle is actually loaded.
document.documentElement.dataset.webpackBundle = 'project';
