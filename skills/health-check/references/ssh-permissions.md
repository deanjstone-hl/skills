# SSH permissions check

Read-only. Nothing is modified. Used by health-check Step 5 and config-audit Step 3.

```bash
stat -c "%a %n" ~/.ssh/id_* ~/.ssh/authorized_keys ~/.ssh/config 2>/dev/null
stat -c "%a %n" ~/.ssh/ 2>/dev/null
stat -c "%a %n" ~/.ssh/*.pub 2>/dev/null
```

Expected:

- `~/.ssh/` is `700`
- Private keys (`id_ed25519`, `id_rsa`, etc.) are `600`
- `authorized_keys` is `600`
- `config` is `600`
- Public keys (`*.pub`) are `644`

Flag anything that deviates. SSH agent connections and remote logins fail silently with
wrong permissions, a common and easy-to-miss cause of "SSH suddenly stopped working."

## Output

One line per file: `✓ <path> (<perm>)` or `✗ <path> (<perm>, expected <expected>)`. A caller
folds that list into its own report row and does not reformat it.
