# Eurovision Vote

A web app for rating and ranking Eurovision performances in real time as you watch the show.

Each performance gets a short text note (to jog your memory), then is slotted into your personal ranking via a binary-search comparison: the app asks "which did you prefer?" until it finds the exact insertion point. The result is a fully ordered personal ranking built up entry by entry.

---

## Structure

```
eurovote/
├── flake.nix                        # Nix dev shell, nix run, Nix package, NixOS module
├── manage.py
├── data/
│   └── <year>/
│       ├── entries.yaml             # Countries, artists, songs, performance order
│       └── images/                  # Entry photos (referenced by entries.yaml)
├── eurovote/
│   ├── settings.py                  # Django settings (all tunable via env vars)
│   ├── urls.py
│   ├── middleware.py                # X-Remote-User header → auto-login (Authelia SSO)
│   └── wsgi.py
└── voting/
    ├── entry_registry.py            # Loads data/<year>/entries.yaml at startup (no DB)
    ├── models.py                    # Vote, RankingEntry (only user data in DB)
    ├── views.py                     # event_list, index, vote_next, compare
    ├── forms.py
    ├── admin.py
    ├── migrations/
    ├── management/commands/
    │   └── ensure_admin.py          # Dev helper: idempotent superuser creation
    └── templates/voting/
        ├── base.html
        ├── login.html
        ├── event_list.html
        ├── index.html
        ├── vote_next.html
        └── compare.html
```

### Key design decisions

**Entry data is not in the database.** Countries, artists, songs and performance order live in `data/<year>/entries.yaml`, checked into git. `voting/entry_registry.py` reads all year directories at Django startup and caches them in memory. Only user-generated data (`Vote`, `RankingEntry`) lives in SQLite. This means no database seed step is needed on deployment.

**Stable entry IDs.** Each entry has an ID of the form `{year}_{country_slug}` (e.g. `2026_united_kingdom`). This is stored on `Vote.entry_id`. The ID is stable across edits to artist name, song title, or image — it only changes if the country name itself changes, which never happens.

**Binary sort ranking.** When a user submits a note for a performance, the app runs a binary-search insertion: it shows two past entries and asks which was better, halving the search space each time. This is a direct port of the original CLI script's `get_ins_index` logic, adapted to work across HTTP requests using Django sessions.

---

## Development

### First time

```bash
nix develop          # enter dev shell (Python + Django + PyYAML)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://localhost:8000. Log in, start voting.

### Updating entry data

Edit `data/<year>/entries.yaml` and restart the server — the registry reloads at startup. No migration or database step required.

To add images, drop files into `data/<year>/images/` and set the `image` field in the YAML to the filename (e.g. `norway.jpg`).

### Adding a new year

Create `data/2027/entries.yaml` following the same format as `data/2026/entries.yaml`. The event list page will show it automatically on next restart.

### Running with nix run

```bash
nix run
```

Migrates and starts the server at `0.0.0.0:8000`. Intended for quick local testing; use the NixOS module for production.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | insecure dev key | Must be set in production |
| `DJANGO_DEBUG` | `true` | Set to `false` in production |
| `ALLOWED_HOSTS` | `localhost 127.0.0.1` | Space-separated list |
| `DJANGO_DB_PATH` | `<repo>/db.sqlite3` | Full path to the SQLite file; set this when the source tree is read-only (Nix store) |

---

## Management commands

### `ensure_admin`

Dev/testing helper: creates a Django superuser if absent, or updates the password if already present. Not needed in production — SSO handles admin access automatically (see below).

```bash
python manage.py ensure_admin --username admin --password <pass>
# or via env vars:
DJANGO_ADMIN_USERNAME=admin DJANGO_ADMIN_PASSWORD=<pass> python manage.py ensure_admin
```

---

## Authentication

### Development (no SSO)

Django's built-in session auth is used. Log in at `/accounts/login/` with the superuser you created via `createsuperuser` or `ensure_admin`.

### Production (Authelia SSO)

`RemoteUserMiddleware` checks for the `X-Remote-User` header on every request. When Authelia is in front, it sets this header to the authenticated username. The middleware auto-creates the Django user if needed and logs them in.

**Admin access in production:** all SSO-authenticated users are automatically granted `is_staff` + `is_superuser` by the middleware. No manual account setup is needed. **Authelia is the gate** — who can access the app and who can access `/admin/` is controlled entirely by Authelia's group/policy rules, not by Django user flags.

The recommended Authelia setup is:
- All authenticated users → allowed to access the app
- Users in your admin LDAP group → additionally allowed to access `/admin/*`

```
# Caddy forward-auth with Authelia (conceptual)
# All routes: require any authenticated Authelia user
# /admin/*:   require Authelia policy that checks admin group membership
```

No code changes are needed to switch between dev and prod modes. When `X-Remote-User` is absent (dev), normal session login is used.

---

## Integrating into a self-hosted NixOS environment (e.g. homey)

The flake exposes a `nixosModules.default` output. Import it from your NixOS flake and enable the service.

### 1. Add as a flake input

In your `flake.nix`:

```nix
inputs = {
  # ... existing inputs ...
  eurovote.url = "github:yourusername/eurovote";
};
```

Pass it through to your NixOS configurations:

```nix
outputs = { self, nixpkgs, eurovote, ... }: {
  nixosConfigurations.your-host = nixpkgs.lib.nixosSystem {
    modules = [
      eurovote.nixosModules.default
      ./hosts/your-host/default.nix
      # ...
    ];
  };
};
```

### 2. Add a SOPS secret

Only one secret is needed: the Django secret key. No admin password secret — SSO handles admin access.

In `secrets/secrets.yaml` (after `sops` editing):

```yaml
eurovote/secret_key: <random 50-char string>
```

In the relevant host module or `modules/services/eurovote.nix`:

```nix
sops.secrets."eurovote/secret_key" = { owner = "root"; };
```

### 3. Enable the service

```nix
services.eurovote = {
  enable        = true;
  port          = 8007;
  allowedHosts  = "localhost 127.0.0.1 vote.yourdomain.com";
  secretKeyFile = config.sops.secrets."eurovote/secret_key".path;
};
```

The service will:
- Run `manage.py migrate` on every start (idempotent — no-op after first run)
- Start `manage.py runserver 127.0.0.1:<port>`
- Write the secret key to an ephemeral `/run/eurovote-secrets.env` that is removed on stop

### 4. Add a Caddy virtual host

```nix
services.caddy.virtualHosts."vote.yourdomain.com" = {
  extraConfig = ''
    reverse_proxy 127.0.0.1:${toString config.services.eurovote.port}
  '';
};
```

If Authelia is already in your Caddy config as a forward-auth layer, the `X-Remote-User` header will be set automatically and SSO will work with no further configuration.

To restrict `/admin/` to your admin LDAP group, add a separate Authelia policy rule for `vote.yourdomain.com/admin*` that requires the admin group before the catch-all rule for general access.

### Uptime monitoring

If using Uptime Kuma (or similar):

```nix
homey.monitoring.monitors = [{
  name     = "Eurovision Vote";
  url      = "https://vote.yourdomain.com";
  interval = 60;
}];
```

### Data directory

The service runs with `DynamicUser = true` and `StateDirectory = "eurovote"`, so the SQLite database lives at `/var/lib/eurovote/db.sqlite3`. Back this up with the rest of your service state.

Entry YAML and images are part of the source tree (in the Nix store), so they are covered by the flake pin and do not need separate backup.
