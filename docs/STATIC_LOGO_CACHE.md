# Static logo/cache fix

The Martins logo, CSS and JavaScript are now served with long-lived browser cache headers:

`Cache-Control: public, max-age=31536000, immutable`

The templates use a stable shared `brand_logo_url` with a file-version query string based on the logo file timestamp. The browser downloads the logo once, keeps it cached, and only downloads it again when the actual logo file changes.

Updated areas:
- Login page logo
- Top bar logo
- Sidebar/dropdown menu logo
- Shared CSS/JS asset helper
- Static file cache headers
