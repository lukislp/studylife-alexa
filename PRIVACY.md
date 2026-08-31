# Privacy Policy for StudyLife (Alexa Skill)

_Last updated: 2026-08-31_

StudyLife is an Alexa Skill that lets you ask about your courses, focus timer, study time,
study programs, goals, and notes on your own, self-hosted [StudyLife](https://github.com/lukislp/studylife)
instance. It is a companion tool for a self-hosted, open-source project - there is no
StudyLife-operated backend or account system behind it, only a small server
([this repository](https://github.com/lukislp/studylife-alexa)) that bridges Alexa's voice
platform to the instance you choose.

## What data this skill handles

- **Your StudyLife instance URL and an account-linking API key** - obtained when you link
  your account in the Alexa app: you enter your own StudyLife instance's address, log in there
  (passkey login/consent, entirely on your own server), and StudyLife issues an API key scoped
  to the permissions listed below. This skill's server stores that key, encrypted at rest, and
  your instance URL, tied to an opaque access/refresh token pair it issues to Alexa's backend -
  see [Data retention](#data-retention) for how long.
- **What you say to Alexa** - Amazon's own Alexa platform performs speech recognition and
  transcription under its own privacy practices; this skill only ever receives the resulting
  text (e.g. a search term for `SearchNotesIntent`, or note content for `CreateNoteIntent`) via
  a standard Alexa Skills Kit request. Voice audio itself never reaches this skill's server.

## What this skill can do on your behalf

Depending on which scopes you grant during linking, this skill can read your course catalog,
live focus-timer state, session history, course goals, study programs and their progress, and
search your notes - and can create new notes. Every one of these is a live, read-only (or, for
creating a note, write) API call to **your own** StudyLife instance, made only in direct response
to something you asked Alexa - never in the background, never on a schedule.

## Where data goes

Every request this skill makes goes to exactly one place: the StudyLife instance URL you
provided when linking your account. **This skill never sends your data to its developer, to
Amazon beyond the standard Alexa Skills Kit request/response, or to any other third party.**
There is no analytics, no telemetry, and no other server involved. The full source is public at
[github.com/lukislp/studylife-alexa](https://github.com/lukislp/studylife-alexa) - every request
this skill makes is visible in [`client.py`](src/studylife_alexa/client.py).

## Data retention

- **Access tokens** (used by Alexa's backend on every request) expire after 1 hour.
- **Refresh tokens** (used to obtain a new access token) expire after 90 days, and are rotated
  (invalidated and replaced) every time they're used.
- Your encrypted API key and instance URL are stored only as long as at least one non-expired
  token references them. Unlinking the skill in the Alexa app stops it from being used
  immediately; the stored record itself is removed once its last token naturally expires,
  within 90 days at the latest.

## Permissions

The specific scopes this skill can request are listed in this repository's
[README](README.md#account-linking) - deliberately narrow (no access to your StudyLife
settings, and nothing beyond what each voice intent actually needs). You choose which of them to
grant when registering the skill as an add-on on your own StudyLife instance.

## Changes to this policy

Any change to this policy is made via a pull request to this repository, visible in its commit
history like any other change.

## Contact

Questions or concerns: open an issue at
[github.com/lukislp/studylife-alexa/issues](https://github.com/lukislp/studylife-alexa/issues).
