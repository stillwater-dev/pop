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
