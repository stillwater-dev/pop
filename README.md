# pop — pop your code onto a VPS

`pop` is a lightweight SSH-based VPS deployment tool. No agent required — just Python, SSH, and YAML playbooks.

## Install

```bash
pip install .
# or for dev:
pip install -e .
```

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
