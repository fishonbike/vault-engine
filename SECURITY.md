# Security Policy

vault-engine is a privacy tool, so we take reports seriously and try to be
unusually honest about what it does and does not protect.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Use GitHub's
private vulnerability reporting:

> Repository → **Security** tab → **Report a vulnerability**

Include a minimal repro and the impact. We aim to acknowledge within a few days
and to coordinate a fix and disclosure timeline with you. There is no bug-bounty
program; credit is given in the advisory unless you prefer otherwise.

In scope, for example:
- a detection bypass that causes real identity to survive into the sanitized
  output in a way the report does not flag;
- mishandling of the reverse map (`*.map.json`) — e.g. it being written somewhere
  it could leak, or emitted in output meant for the cloud;
- command-injection / path-traversal / unsafe file handling in the CLI;
- the `openai-compat` provider sending data anywhere other than the configured
  endpoint.

## Operational red line — the reverse map

The `*.map.json` reverse map **is** the identity it hides; it is the only thing
that links tokens back to real people.

- Keep it local. **Never** send it to a cloud model and **never** commit it.
- `.gitignore` excludes `*.map.json` by default and the CLI prints a reminder on
  every run. Use `--one-way` to produce no map at all.

Treat a leaked map as a full disclosure of the underlying data.

## Threat model & limitations

vault-engine reduces identity exposure; it does not provide a mathematical
guarantee of anonymity. Specifically:

- **LLM detection is best-effort.** A model can miss a name or a rare
  quasi-identifier. This is *not* k-anonymity or differential privacy.
- **Quasi-identifiers and writing style are out of scope.** A unique combination
  of non-name facts, or a distinctive writing voice, can still re-identify even
  with names removed. Use `--policy max` for higher-stakes material.
- **If the model backend fails, the run degrades to regex-only and exits
  non-zero** (unless `--allow-degraded`) — it will not silently ship
  under-redacted text, but you must still heed the warning.
- **The `openai-compat` provider sends raw text to your endpoint** (it is the
  detector). The default local provider exists precisely to avoid that.

See the README's "Threat model & limitations" for the full picture. Always
review the generated risk report before sending anything to a third party.

## Supported versions

Security fixes target the latest release on the default branch. Pin a version
you have reviewed for sensitive use.
