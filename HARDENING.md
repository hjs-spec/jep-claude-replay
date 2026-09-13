# Implementation hardening — September 2026

Bind replay verification to trusted keys and the actual archive/evidence contents.

## Changes

Ed25519 uses cryptography/OpenSSL. Single-event and bulk signing share the same payload. Keyring verifies against configured keys, with public_verifier() for public-key-only checks. Unsigned archives do not pass signature verification. Evidence digests are recomputed. Imports revalidate archive contents and manifest artifacts instead of trusting embedded reports, and reject unsafe/duplicate ZIP paths. Evidence filenames remain unique within packs. New events omit content previews by default; opt-in previews redact values. UI fields are escaped. Verification, pack and unpack CLI failures return nonzero.

## Validation

```sh
python -m pytest -q
```

## Compatibility and remaining limits

Existing golden hashes/signatures remain unchanged. The legacy canonicalizer is explicitly documented as archive-specific, not full RFC 8785. New preview defaults change newly recorded events only. Unpack accepts an optional trusted keyring; an embedded report is returned separately as untrusted provenance. Output directories must be empty. Public keys must be explicitly trusted; an empty Keyring no longer trusts keys supplied inside events.
