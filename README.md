# paseo-hermes-relay

`paseo-hermes-relay` is the standalone repository for the
`paseo-review-relay` Hermes user plugin. The plugin routes an anchored Telegram
reply to the exact persistent Paseo PR owner and review revision that created
the alert. It is a transport boundary: it never approves, merges, chooses a
different owner, or expands prior authority.

The plugin is standard-library Python, registers only `pre_gateway_dispatch`,
and stores its private delivery map in SQLite under the Hermes plugin-data
directory. See [docs/spec.md](docs/spec.md) for the accepted behavior and
security boundary.

## Requirements

- Python 3.11 or newer
- Hermes with user-plugin support
- `paseo` and `gh` available to the Hermes gateway process
- A persistent local Paseo owner for each real decision

## Installation

Check out a reviewed tag and its pinned commit directly at the Hermes plugin
path. Do not install from a moving branch.

```bash
plugin_root="$HOME/.hermes/plugins/paseo-review-relay"
git clone REPOSITORY_URL "$plugin_root"
git -C "$plugin_root" checkout --detach REVIEWED_40_HEX_COMMIT
```

Then run the following local setup. It is safe to rerun: it preserves an
existing private configuration and the mode of an existing `~/.local/bin`,
and it refuses to replace a different CLI target.

```bash
bin_dir="$HOME/.local/bin"
cli_link="$bin_dir/hermes-relay"
wrapper="$plugin_root/hermes-relay"
mkdir -p "$bin_dir"

if test -L "$cli_link"; then
  if test "$(readlink -f "$cli_link")" != "$(readlink -f "$wrapper")"; then
    echo "Refusing to replace a symlink to a different wrapper: $cli_link" >&2
    exit 1
  fi
elif test -e "$cli_link"; then
  echo "Refusing to replace a non-symlink CLI: $cli_link" >&2
  exit 1
else
  ln -s "$wrapper" "$cli_link"
fi

data_root="$HOME/.hermes/plugin-data/paseo-review-relay"
config_path="$data_root/config.json"
install -d -m 700 "$data_root"
if ! test -e "$config_path"; then
  install -m 600 "$plugin_root/config.example.json" "$config_path"
fi
chmod 600 "$config_path"
```

The CLI must be a symlink, not a copied wrapper. `hermes-relay` resolves its
real file location with `Path(__file__).resolve()` so its package-relative
imports load from the plugin checkout. On first installation, replace all three
configuration placeholders without printing their values. Then enable and
validate the plugin:

```bash
hermes plugins enable paseo-review-relay --no-allow-tool-override
hermes plugins doctor "$plugin_root" --ci
hermes-relay doctor
```

Restart only the Hermes gateway if plugin discovery requires it. Paseo does
not need restarting.

### Haoshoku-managed VPS setup

For a Haoshoku-managed VPS, use Haoshoku's pinned `--server-hermes-relay`
setup workflow once that Haoshoku change is released. It verifies the selected
tag and commit, deploys only the plugin allowlist, preserves private config and
SQLite data, creates the required CLI symlink, and runs both doctor checks.
This repository does not install Hermes, write VPS state, or update Haoshoku.

## Updates and rollback

Before changing the pinned plugin commit, inspect active work and quiesce the
Hermes gateway. Back up the complete plugin directory, Hermes `config.yaml`,
and the complete `plugin-data/paseo-review-relay` directory so the SQLite
database and any WAL files remain together.

To roll back, disable only `paseo-review-relay`, restore the reviewed plugin
directory and Hermes configuration, re-enable the plugin, run both doctor
checks, and restart only the Hermes gateway if discovery requires it. Do not
delete or automatically replace `relay.sqlite3` during rollback. Preserve the
current database, WAL files, and backups for audit; restoring an older database
requires explicit owner authorization.

## Private configuration

`config.json` must contain non-empty, non-placeholder strings and have mode
0600:

```json
{
  "telegramChatId": "YOUR_PRIVATE_DM_CHAT_ID",
  "telegramUserId": "YOUR_PRIVATE_TELEGRAM_USER_ID",
  "serverId": "YOUR_LOCAL_PASEO_SERVER_ID"
}
```

The IDs belong only in
`~/.hermes/plugin-data/paseo-review-relay/config.json`; never commit that file.
Missing, unreadable, malformed, permissive, or placeholder configuration leaves
the hook inert. `hermes-relay doctor` validates the private configuration and
the SQLite database without making external calls.

## Reply workflow

Open a decision from a private UTF-8 JSON request file:

```bash
hermes-relay open --request-file /private/path/request.json
```

The request identifies the decision, persistent owner, local server,
repository, pull request, exact 40-character head and base revisions, proposal,
consequence, recommendation, and question. The resulting Telegram message is
the reply anchor.

An exact whole-message `approve`, `reject`, or `hold` is recorded as a decision
receipt for that proposal only. Every other eligible text reply is a question.
The owning Paseo driver must still revalidate the receipt and live revision
before acting.

Operator commands:

```bash
hermes-relay answer DECISION_ID --file /private/path/answer.txt
hermes-relay supersede OLD_DECISION_ID --request-file /private/path/revision.json
hermes-relay pending
hermes-relay close DECISION_ID
hermes-relay retry FAILED_ATTEMPT_ID
```

`pending` should be checked on later owner runs. For a `blocked` or
`uncertain` decision, inspect and reconcile the actual Telegram, Paseo, and
GitHub evidence. Never retry or replay an ambiguous or uncertain attempt. If
verified transport should continue, close the old decision and open a fresh
request with a new decision ID, the current revisions, and the verified
persistent owner. `retry` accepts only definite failed sends. A successful send
means the platform returned a message ID, not that the user read it.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 tests/run.py
python3 -m compileall -q .
```

The suite has no third-party dependencies. CI uses `tests/run.py` to fail if
fewer than 54 tests are discovered.
