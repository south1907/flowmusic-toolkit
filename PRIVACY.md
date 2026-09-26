# Privacy Policy

Last updated: September 26, 2026

This policy describes the default behavior of the Unofficial Flow Music Local
API and its companion Chrome extension. It applies to the code in this
repository as distributed. A person who modifies or hosts the software must
document any different data practices they introduce.

## Local processing

The API is designed to run on the user's computer and binds to
`127.0.0.1:8123` by default. The project has no analytics, advertising,
telemetry, or developer-operated data collection service.

The local API processes and stores generation information such as:

- prompts submitted to the API;
- local and provider job, project, operation, and clip identifiers;
- generation status, timestamps, result metadata, and error details; and
- download metadata for generated audio.

This information is stored in the local SQLite database at
`data/google-flow-music.db` by default. Generated audio is streamed on request
and is stored only when the user or an API client saves the downloaded file.

## Browser session data

The extension uses the session already active in the user's Flow Music tab.
Flow Music cookies and access tokens are read and used only inside that page's
browser context to make the requested first-party calls. They are not included
in WebSocket messages, sent to the Python API, or stored in its SQLite database
by the unmodified project.

The extension stores only its local bridge connection state and latest error in
Chrome extension storage. It does not intentionally persist Flow Music cookies,
access tokens, or Google passwords.

## Third-party processing

Prompts and generation requests are sent to Flow Music because that processing
is necessary to provide the requested functionality. Google's handling of that
data is governed by the applicable service terms and the
[Google Privacy Policy](https://policies.google.com/privacy), not by this
project. Generated download links may also cause Flow Music to receive the
normal request data associated with a download.

The project does not sell personal information or provide Flow Music access to
third parties. It does not include a hosted relay operated by the project
maintainers.

## Retention and deletion

Local job records remain in the SQLite database until the user deletes the
database or implements another retention policy. To remove all default local
job records, stop the API and delete `data/google-flow-music.db`. Delete any
downloaded audio separately. Chrome's extension settings can be removed by
clearing the extension's site data or uninstalling the extension.

Deleting local records does not delete data held by Google or Flow Music. Use
the controls provided by those services for third-party records.

## Security and user choices

Keep the API bound to a loopback address unless you have added authentication,
transport security, and appropriate access controls. Do not expose port `8123`
to a public or untrusted network. Only install the extension from code you have
reviewed, and monitor account credit usage while automation is active.

Prompts may contain personal, confidential, or copyrighted information. Submit
such information only when you have the right to do so and accept the relevant
service's data handling terms.

Questions and security reports should be submitted through the repository's
issue tracker. Do not include passwords, cookies, access tokens, private
prompts, or other sensitive information in a public issue.
