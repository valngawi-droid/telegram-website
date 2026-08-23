// PallBot — shared helpers
document.addEventListener('DOMContentLoaded', () => {
  // auto-hide status pill pulse (cosmetic)
  const pill = document.querySelector('.status-pill');
  if (pill && !pill.classList.contains('on')) {
    pill.style.animation = 'none';
  }
});
