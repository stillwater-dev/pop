# pop — pop your code onto a VPS

`pop` is a lightweight SSH-based VPS deployment tool. No agent required — just Python, SSH, and YAML playbooks.

## Install

```bash
pip install .
# or for dev:
pip install -e .
```

## CI/CD

GitHub Actions now handles two automation paths:

- `CI` on every push to `main`, every pull request, and manual `workflow_dispatch`
- `Release` on tags matching `v*` and manual `workflow_dispatch`

The CI workflow runs:

```bash
python -m pip install -e .[dev]
python -m pytest -q tests/test_dev.py tests/test_dreamwave.py tests/test_bachelor.py
python -m compileall pop tests
python -m pop.cli --help
python -m build --sdist --wheel
```

It also publishes package artifacts from `dist/` and includes a stable `required-checks` gate job so branch protection can later target one fixed check name.

To cut a release, create and push a semantic tag such as `v0.1.1`:

```bash
git tag v0.1.1
git push origin v0.1.1
```

That release workflow builds the wheel and source distribution, uploads them as workflow artifacts, and attaches them to a GitHub Release automatically. A manual `Release` run without a tag input performs build-only verification and uploads artifacts, but skips GitHub Release creation.

## Config

Create `~/.pop.yaml`:

```yaml
servers:
  - name: raff
    host: <IP>
    user: root
    key: ~/.ssh/id_rsa

  - name: deluxhost
    host: <IP>
    user: root
    password: <password>   # key OR password, not both
```

## Usage

```bash
pop list                           # list servers
pop run raff "uptime"              # run a command
pop exec raff ./setup.sh           # upload + run local script
pop upload raff ./file.txt /tmp/   # upload a file
pop deploy raff docker             # run a playbook
pop deploy raff nginx              # run nginx playbook
pop deploy raff /path/my.yaml      # custom playbook
pop connect raff                   # interactive SSH
```

## Playbooks

Bundled playbooks in `playbooks/`:

- **docker** — Docker + Docker Compose
- **nginx** — Nginx + Let's Encrypt
- **basic** — Server hardening (ufw, fail2ban, updates)
- **deploy** — Generic app deployment from git

### Playbook format

```yaml
vars:
  app_dir: /opt/app
  docker_user: ubuntu

steps:
  - name: Install Docker
    command: curl -fsSL https://get.docker.com | sh
  - name: Create app directory
    command: mkdir -p {{ app_dir }}
    cwd: /opt
```

Variables: `{{ var_name }}` or `{{var_name}}` — both work.

## Config file location

Default: `~/.pop.yaml`
Override: `pop -c /path/to/config.yaml ...`

## DREAMWAVE FM Commands

DREAMWAVE FM is a vaporwave web radio app deployed at `38.45.71.55`. The `pop dreamwave` subcommand manages it directly — no config file needed.

```bash
pop dreamwave status           # backend + nginx status
pop dreamwave restart          # restart backend service
pop dreamwave logs -n 50       # tail backend logs
pop dreamwave reload           # reload nginx
pop dreamwave tracks -n 20     # list tracks on VPS
pop dreamwave deploy /root/vaporwave-radio              # deploy frontend only
pop dreamwave deploy --dry-run /root/vaporwave-radio    # preview rsync changes
pop dreamwave deploy-tracks    # deploy from /root/vaporwave-radio/tracks/
pop dreamwave deploy-tracks /path/to/local/tracks/  # custom source
pop dreamwave health          # API health check
pop dreamwave exec "command"   # run arbitrary command on VPS
```

### DREAMWAVE Stack
- **VPS**: 38.45.71.55 (Little Creek)
- **Frontend**: nginx → `/var/www/dreamwave/` (static files)
- **Backend**: FastAPI on port 8001 (systemd `dreamwave-backend`)
- **Database**: PostgreSQL
- **Domain**: `dream.lewd.win`
- **Tracks**: 94 MP3s (~1.7GB) at `/var/www/dreamwave/tracks/`
- **SSH key**: `/root/.ssh/id_ed25519`


## Bachelor Party App Commands

Bachelor Olympics app for the May 2026 Wilmington trip. Served on port 8765, accessible via localtunnel at `https://wilmington-bachelor.loca.lt`.

```bash
pop bachelor status          # check server + tunnel status
pop bachelor start          # start HTTP server
pop bachelor stop           # stop HTTP server
pop bachelor restart        # restart HTTP server
pop bachelor tunnel-start  # start localtunnel
pop bachelor tunnel-stop   # stop localtunnel
pop bachelor tunnel-restart
pop bachelor full-restart  # server + tunnel
pop bachelor health        # check app responds
pop bachelor exec "ls js/" # run command in app dir
```

### Bachelor App Stack
- **Local dev**: `python3 -m http.server 8765` from `/root/bachelor_party/`
- **Tunnel**: localtunnel → `https://wilmington-bachelor.loca.lt`
- **App dir**: `/root/bachelor_party/`
- **Port**: 8765
- **Tunnel port**: 7400 (lt proxies 8765 → public 443)


## Dev Container Commands

Persistent remote dev container on the Bachelor VPS (`5.181.177.113`). Good for keeping project dependencies isolated while reusing the same container across sessions.

```bash
pop dev status
pop dev start
pop dev stop
pop dev restart
pop dev recreate
pop dev bootstrap
pop dev info
pop dev workspace
pop dev doctor
pop dev doctor --fix
pop dev shell
pop dev ps
pop dev logs --lines 100
pop dev exec pwd
pop dev exec --workspace bachelor_party pwd
pop dev exec --workspace pop -- ls -la      # use -- when the inner command starts with its own flags
pop dev exec --workspace dreamwave-fm git status --short
```

### Dev Container Workspaces
- `pop` → `/workspace/pop`
- `bachelor_party` → `/workspace/bachelor_party`
- `dreamwave-fm` → `/workspace/dreamwave-fm`

The container image is `python:3.13-slim`. `pop dev bootstrap` and `pop dev doctor --fix` refresh `git`, `python3-pip`, `procps`, `pytest`, and `pytest-mock` inside the container; `pop dev start` bootstraps them when it has to create or start the container.

`pop dev shell` opens an interactive `/bin/bash` inside the running container. `pop dev exec ...` now propagates the inner command's exit status back to your shell, so automation can fail fast on container-side errors.

`pop dev bootstrap` is the quickest one-shot setup command: it starts the container if needed, refreshes the toolchain, and prints the same health summary as `pop dev doctor`.
