// Global entry (#466). Still no scripts: until #468 moves them here the classic
// `{% compress js %}` block in base.html does the work. The marker lets the E2E suite and a
// curious human check that the bundle is actually loaded.
import '../scss/project.scss';

document.documentElement.dataset.webpackBundle = 'project';
