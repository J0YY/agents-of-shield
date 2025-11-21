// Intentionally leaked frontend key for demo purposes
const PUBLIC_ANALYTICS_KEY = 'sk_test_12345';

window.addEventListener('DOMContentLoaded', () => {
  console.log('Pet Grooming dashboard booted with key:', PUBLIC_ANALYTICS_KEY);

  // Fake beacon that pretends to log client-side errors
  if (window.location.pathname === '/admin') {
    fetch('/debug').then(() => {
      console.log('Diagnostics ping sent');
    });
  }
});
