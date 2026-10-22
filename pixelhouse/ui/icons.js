/* Small vector glyphs retain the prototype's shapes at every window scale. */
(() => {
  const svg = (body, viewBox = '0 0 32 32') =>
    `<svg class="ui-icon" viewBox="${viewBox}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${body}</svg>`;
  const stroke = 'fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="square" stroke-linejoin="miter"';
  const glyphs = [
    ['.nav-btn:nth-child(1) .nav-icon', svg('<path fill="#49e8ff" d="M3 3h7v7H3zm10 0h7v7h-7zm10 0h7v7h-7zM3 13h7v7H3zm10 0h7v7h-7zm10 0h7v7h-7zM3 23h7v7H3zm10 0h7v7h-7zm10 0h7v7h-7z"/><path fill="#718cff" d="M6 6h4v4H6zm10 10h4v4h-4zm10 10h4v4h-4z"/>')],
    ['.nav-btn:nth-child(2) .nav-icon', svg('<path fill="#a8caff" d="M3 18h6v11H3zm10-9h6v20h-6zm10-16h6v36h-6z" transform="translate(0 7)"/><path fill="#f1f4ff" d="M5 21h2v8H5zm10-9h2v17h-2zm10-15h2v32h-2z" transform="translate(0 7)"/>')],
    ['.nav-btn:nth-child(3) .nav-icon', svg(`<circle cx="16" cy="16" r="5" ${stroke}/><path ${stroke} d="M16 2v5m0 18v5M2 16h5m18 0h5M6 6l4 4m12 12 4 4M26 6l-4 4M10 22l-4 4"/>`)],
    ['.gallery-tab:nth-child(1) span', svg('<path fill="currentColor" d="m13 1 2 8 7 2-7 2-2 8-2-8-7-2 7-2zm11 14 1.5 4.5L30 21l-4.5 1.5L24 27l-1.5-4.5L18 21l4.5-1.5zM6 23l1 3 3 1-3 1-1 3-1-3-3-1 3-1z"/>')],
    ['.gallery-tab:nth-child(2) span', svg('<path fill="#e8efff" d="m4 24 18-18 5 5L9 29H4z"/><path fill="#a3c2ff" d="m4 24 5 5H4zm20-20 4 4-2 2-4-4z"/><path d="m20 8 5 5" stroke="#26427f" stroke-width="2"/>')],
    ['.gallery-tab:nth-child(3) span', svg(`<path ${stroke} d="M2 9V6h11l3 3h14v18H2z"/><path ${stroke} d="M2 13h28M7 23l6-7h15"/>`)],
    ['.gallery-tab:nth-child(4) span', svg(`<path ${stroke} d="M16 3v5m-3-5h6M5 10h22v18H5zM2 15h3m22 0h3M11 18h2m6 0h2M11 24h10"/><circle cx="12" cy="18" r="1.5" fill="currentColor"/><circle cx="20" cy="18" r="1.5" fill="currentColor"/>`)],
    ['.gallery-tab:nth-child(5) span', svg('<path fill="currentColor" d="M3 5h26v4H3zm11 4h4v18h-4zM9 27h14v3H9z"/>')],
    ['.gallery-tab:nth-child(6) span', svg(`<path ${stroke} d="M10 23c0-4-5-6-5-12a11 11 0 0 1 22 0c0 6-5 8-5 12zM10 26h12m-10 3h8"/><path ${stroke} d="m12 18 4 3 4-3"/>`)],
    ['.keyboard-icon', svg(`<path ${stroke} d="M2 3h88v42H2zM6 7h80v26H6zM9 39h64" />${Array.from({length: 5}, (_, row) => Array.from({length: 11 - (row === 4 ? 2 : 0)}, (_, col) => `<rect x="${10 + col * 7}" y="${10 + row * 5}" width="4" height="2" fill="currentColor"/>`).join('')).join('')}`, '0 0 92 48')],
    ['#device-card .sun', svg(`<circle cx="16" cy="16" r="6" ${stroke}/><path ${stroke} d="M16 2v5m0 18v5M2 16h5m18 0h5M6 6l4 4m12 12 4 4M26 6l-4 4M10 22l-4 4"/>`)]
  ];
  for (const [selector, markup] of glyphs) {
    const element = document.querySelector(selector);
    if (element) element.innerHTML = markup;
  }
})();
