// Page entry (#467): the stylesheets this page loads after the global bundle, so its equal-specificity
// `!important` rules still win on order (#250). Page scripts join it in #468.
// flatpickr's own sheet comes first, as the vendored copy did: suchar_form.scss restyles it.
import 'flatpickr/dist/flatpickr.min.css';
import '../../scss/pages/suchar_form.scss';
