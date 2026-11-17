# Privacy Policy for StudyAtrium (Alexa Skill)

_Last updated: 2026-11-17_

StudyAtrium is an Alexa Skill that lets you ask about your courses, focus timer, study time,
study programs, goals, and notes on your own, self-hosted [StudyAtrium](https://github.com/lukislp/studylife)
instance. It is a companion tool for a self-hosted, open-source project - there is no
StudyAtrium-operated backend or account system behind it, only a small server
([this repository](https://github.com/lukislp/studylife-alexa)) that bridges Alexa's voice
platform to the instance you choose.

## What data this skill handles

- **Your StudyAtrium instance URL and an account-linking API key** - obtained when you link
  your account in the Alexa app: you enter your own StudyAtrium instance's address, log in there
  (passkey login/consent, entirely on your own server), and StudyAtrium issues an API key scoped
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
creating a note, write) API call to **your own** StudyAtrium instance, made only in direct response
to something you asked Alexa - never in the background, never on a schedule.

## Where data goes

Every request this skill makes goes to exactly one place: the StudyAtrium instance URL you
provided when linking your account. **This skill never sends your data to its developer, to
Amazon beyond the standard Alexa Skills Kit request/response, or to any other third party.**
There is no analytics, no telemetry, and no other server involved. The full source is public at
[github.com/lukislp/studylife-alexa](https://github.com/lukislp/studylife-alexa) - every request
this skill makes is visible in [`client.py`](src/studylife_alexa/client.py).

## Data retention

- **Authorization codes** (used once, during linking) expire after 5 minutes.
- **Access tokens** (used by Alexa's backend on every request) expire after 1 hour.
- **Refresh tokens** (used to obtain a new access token) expire after 90 days, and are rotated
  (invalidated and replaced) every time they're used.
- **Pending link requests** (the short step between choosing your instance and finishing the
  login) are discarded after 10 minutes. They contain no API key.
- An hourly cleanup job permanently deletes every expired code and token. An access token is
  therefore gone at most about 2 hours after it was issued, and a refresh token at most 90 days
  plus about 1 hour after it was issued.
- Your encrypted API key and instance URL are stored only inside those records, so they are
  removed with the last of them. Unlinking the skill in the Alexa app stops it from being used
  immediately; the stored records are then removed when they expire, within 90 days at the latest.
- **Deleting your StudyAtrium account** also removes this skill's records for you right away:
  your StudyAtrium server tells this add-on to delete every code and token that holds one of
  your API keys. This works when your instance is configured to send that request; if it is not,
  or the add-on is unreachable at that moment, the records still disappear on expiry as above.
  The API key itself is revoked with your account, so it is unusable either way.

## Permissions

The specific scopes this skill can request are listed in this repository's
[README](README.md#account-linking) - deliberately narrow (no access to your StudyAtrium
settings, and nothing beyond what each voice intent actually needs). You choose which of them to
grant when registering the skill as an add-on on your own StudyAtrium instance.

## Changes to this policy

Any change to this policy is made via a pull request to this repository, visible in its commit
history like any other change.

## Contact

Questions or concerns: open an issue at
[github.com/lukislp/studylife-alexa/issues](https://github.com/lukislp/studylife-alexa/issues).
