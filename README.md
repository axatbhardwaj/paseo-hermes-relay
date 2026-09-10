# paseo-hermes-relay

`paseo-hermes-relay` is a Hermes user plugin that routes an anchored Telegram
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

install -d -m 700 "$HOME/.local/bin"
ln -s "$plugin_root/hermes-relay" "$HOME/.local/bin/hermes-relay"
```

The CLI must be a symlink, not a copied wrapper. `hermes-relay` resolves its
real file location with `Path(__file__).resolve()` so its package-relative
imports load from the plugin checkout.

Create the private configuration before enabling the plugin:

```bash
data_root="$HOME/.hermes/plugin-data/paseo-review-relay"
install -d -m 700 "$data_root"
install -m 600 "$plugin_root/config.example.json" "$data_root/config.json"
```

Replace all three placeholders without printing their values, then enable and
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

`pending` should be checked on later owner runs. `retry` accepts only definite
failed sends; ambiguous sends are never replayed automatically. A successful
send means the platform returned a message ID, not that the user read it.

## Development

```bash
python3 -m unittest discover -s tests/hermes_review_relay -v
python3 -m compileall -q .
```

The suite has no third-party dependencies.
