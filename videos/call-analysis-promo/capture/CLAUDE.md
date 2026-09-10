# Call Analysis — NVIDIA Contact Center Intelligence

Source: http://127.0.0.1:8787/

To create a video from this capture, use the `product-launch-video` skill.

## What's in This Capture

| File | Contents |
|------|----------|
| `screenshots/contact-sheet.jpg` | **View this first.** All scroll screenshots in labeled grid — see the entire page at a glance |
| `screenshots/scroll-*.png` | Individual viewport screenshots if you need detail on a specific section. |
| `extracted/tokens.json` | Design tokens: 18 colors, 2 fonts, 11 headings, 0 CTAs |
| `extracted/design-styles.json` | Computed styles from live DOM: typography hierarchy, button/card/nav styles, spacing scale, border-radius, box shadows. Primary data source for DESIGN.md. |
| `extracted/asset-descriptions.md` | One-line description of every downloaded asset. Read this for asset selection — only open individual files for safe-zone checking. |
| `extracted/visible-text.txt` | Page text in DOM order, prefixed with HTML tag (`[h1]`, `[p]`, `[a]`). Use as context — rephrase freely. |
| `assets/contact-sheet.jpg` | All downloaded images in one labeled grid. |
| `assets/` | Individual downloaded images, SVGs, and font files. |

## Brand Summary

- **Colors**: #E8E8EF (bg-light), #1A1A26 (surface-dark), #0A0A0F (surface-dark), #8B8BA3 (neutral), #16161F (surface-dark), #76B900 (accent), #1A2A0A (accent), #0D1A2A (accent), #2A2A3D (surface-dark), #000000 (bg-dark)
- **Fonts**: Segoe UI (400,600,700), Arial (600)
