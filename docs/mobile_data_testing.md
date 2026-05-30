# Mobile Data Testing

Remote phone testing does not require the phone and development machine to share
the same Wi-Fi or LAN. For mobile data, use a public HTTPS development URL from a
tunnel, preview deployment, or staging deployment.

Do not expose `/admin/` publicly unless authentication is enabled. When remote
mobile testing is enabled in `DEBUG`, Sourceflow shows a development warning
banner on rendered pages.

## A. Cloudflare Tunnel

Start Django on loopback only:

```bash
python manage.py runserver 127.0.0.1:8000
```

Start the tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Configure the generated HTTPS URL:

```bash
set ENABLE_REMOTE_MOBILE_TESTING=True
set DEV_PUBLIC_BASE_URL=https://GENERATED.trycloudflare.com
set DEV_EXTRA_ALLOWED_HOSTS=GENERATED.trycloudflare.com
set DEV_CSRF_TRUSTED_ORIGINS=https://GENERATED.trycloudflare.com
set DEV_TUNNEL_PROVIDER=cloudflare
```

Restart Django after changing the environment.

## B. ngrok

Start Django on loopback only:

```bash
python manage.py runserver 127.0.0.1:8000
```

Start ngrok:

```bash
ngrok http 8000
```

Configure the generated HTTPS URL:

```bash
set ENABLE_REMOTE_MOBILE_TESTING=True
set DEV_PUBLIC_BASE_URL=https://GENERATED.ngrok-free.app
set DEV_EXTRA_ALLOWED_HOSTS=GENERATED.ngrok-free.app
set DEV_CSRF_TRUSTED_ORIGINS=https://GENERATED.ngrok-free.app
set DEV_TUNNEL_PROVIDER=ngrok
```

Restart Django after changing the environment.

## C. Preview Or Staging Deployment

For serious mobile testing, use a temporary HTTPS preview or staging deployment.
The app should work behind a reverse proxy and HTTPS. Keep production settings
strict: exact `ALLOWED_HOSTS`, exact `CSRF_TRUSTED_ORIGINS`, no wildcard hosts,
and no `DEBUG=True`.

## Helper Commands

Print the active local and public mobile URLs:

```bash
python manage.py print_remote_mobile_test_urls
```

Print the public URL for QR scanning:

```bash
python manage.py print_mobile_qr
```

The `qrcode` package is optional. If it is unavailable, the command prints the
plain URL.

## Remote Mobile Testing Checklist

- Start Django locally on `127.0.0.1:8000`
- Start tunnel
- Copy generated HTTPS URL
- Set `DEV_PUBLIC_BASE_URL`
- Set `DEV_EXTRA_ALLOWED_HOSTS`
- Set `DEV_CSRF_TRUSTED_ORIGINS`
- Restart Django
- Open public HTTPS URL on phone using mobile data
- Run Playwright with `E2E_BASE_URL` set to the same public URL

Example:

```bash
set ENABLE_REMOTE_MOBILE_TESTING=True
set DEV_PUBLIC_BASE_URL=https://GENERATED.trycloudflare.com
set DEV_EXTRA_ALLOWED_HOSTS=GENERATED.trycloudflare.com
set DEV_CSRF_TRUSTED_ORIGINS=https://GENERATED.trycloudflare.com
set E2E_BASE_URL=https://GENERATED.trycloudflare.com
```

Same-Wi-Fi or LAN testing is optional. Do not rely on `localhost`,
`127.0.0.1`, or a LAN IP for phone testing over mobile data.
