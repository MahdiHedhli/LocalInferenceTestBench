# Security and privacy

This project assumes the repository will be public and the inference endpoint will be private.

## Data that never belongs in tracked content

- API keys, bearer tokens, cookies, private keys, or environment-file contents;
- private network addresses, internal domains, machine names, account names, or topology;
- absolute user-directory paths, inventory IDs, serial numbers, MAC addresses, or screenshots;
- raw prompts, completions, reasoning, tool arguments, traces, logs, or packet captures; and
- real model-run artifacts copied from a private environment.

Examples use loopback, `example.com`, and standards-reserved documentation addresses. Local values
belong in ignored files under `.local/` or in process environment variables.

## Three publication barriers

1. **Local privacy gate**: scans the exact staged index before commit and the complete tracked tree
   before push. It checks generic identifier patterns, current machine/account identifiers collected
   at runtime, dangerous file types, symlinks, and an ignored custom literal denylist.
2. **Secret scanner**: Gitleaks runs locally and in continuous integration with redacted output.
3. **Host protection**: GitHub secret scanning and repository push protection are enabled on the
   public repository.

Continuous integration is a backstop, not a confidentiality boundary: content has already reached the
host by the time CI sees it. Keep the local hooks installed.

## Local denylist

Run `scripts/install-hooks` once per clone. It creates `.local/privacy-denylist.txt` from the
comments-only example with owner-only permissions where supported. Add one literal identifier per
line, including private project codenames, host labels, internal domains, and other values that a
generic scanner cannot recognize. Do not put credentials in this file.

Strict publication checks fail closed if the denylist is missing, empty, tracked, not covered by a
Git ignore rule, or group/world-accessible. Findings report only rule, path, and line number—never the
matching value. This makes a new clone explicitly establish its own environment boundary before
publication.

## Credential handling

The reference runner accepts a credential from the environment name declared by the local manifest.
An optional env file is a path argument, not a secret argument, and must be owner-only on platforms
that expose POSIX modes. Credentials are held in memory only for the request and are never reported.
Endpoints containing URL credentials, query strings, fragments, public addresses, or unresolved
names are rejected.

## Result minimization

Run artifacts are ignored and owner-only where supported. They contain model provenance, aggregate
usage/performance, categorical routing, and boolean checks. They do not contain the text used to
derive those values or a reusable fingerprint of that text. A repeatability experiment may compare
responses transiently and retain only a stability boolean.

Before deliberately publishing a result:

1. export only fields permitted by the run-record schema;
2. replace any local runtime selector with its public artifact identity;
3. put the export in a clean temporary directory;
4. run the full privacy and secret scans again; and
5. have another person review the diff.

## If a leak is detected

Stop publishing. Rotate an exposed credential first, then remove the data from the branch and hosted
history. Do not paste the value into an issue, pull request, chat, or scanner log. Follow the hosting
provider's sensitive-data removal process and document only the category and remediation status.
