# Security policy

## Reporting a vulnerability

Please report security issues privately to **philip@decentsoftwa.re** rather
than opening a public issue. Include what you did, what happened, and how bad
you think it is; a proof of concept helps. You will get an acknowledgement
within a few days.

Please do not test against instances you do not own — real recordings of real
people may be on them.

## What this app handles

Citizens stores audio recordings of people speaking, their transcripts, and API
keys for third-party services. Issues touching any of the following are treated
as high severity:

* access to another organizer's assemblies, recordings or transcripts
* any path that lets an unauthenticated caller reach organizer or admin routes
* exposure of a provider API key (in responses, logs, or the client bundle)
* recorder invite tokens leaking, or being guessable
* audio or transcripts reaching a third party that the administrator did not configure

## Design notes relevant to security

* Authentication is enforced by the AppAPI proxy through the route access levels
  declared in `appinfo/info.xml`; admin routes are `ADMIN`, table-phone routes
  are `PUBLIC` and everything else requires a logged-in user.
* Recorder invites are verified by SHA-256 hash; the token is additionally kept
  encrypted with the app secret so QR sheets can be re-displayed.
* API keys live in Nextcloud's app configuration marked *sensitive*, and the
  logging pipeline redacts anything that looks like a secret.
* `CITIZENS_INSECURE_NO_AUTH` exists for local browser tests and is ignored
  unless the configured Nextcloud is a loopback address.

## Supported versions

This is a beta; fixes land on the latest release only.
