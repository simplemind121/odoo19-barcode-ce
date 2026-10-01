# Security policy

## Supported versions

Security fixes are made on the `main` branch and released as a new module
version. Older versions are not patched.

| Version | Supported |
| --- | --- |
| 2.1.x (`stock_barcode_ce` 19.0.2.1.x) | Yes |
| 2.0.x and earlier | No. Upgrade to 2.1. |

## Reporting a vulnerability

Do not report security problems in public issues, pull requests or
discussions.

Report them privately through GitHub:
**Security** tab → **Report a vulnerability**, or open
<https://github.com/simplemind121/odoo19-barcode-ce/security/advisories/new>.

Include, as far as you can:

*   the affected module and version;
*   the role of the attacking user (operator, supervisor, inventory user,
    unauthenticated);
*   steps to reproduce, or a proof of concept;
*   the impact you expect (data read, data changed, privilege gained).

What to expect:

*   an acknowledgement within 7 days;
*   an assessment and a plan within 30 days;
*   credit in the release notes when the fix ships, unless you prefer to stay
    anonymous.

Please give the maintainers a reasonable time to release a fix before you
disclose the problem publicly.

## Trust model

Read this before you grant the scanner roles.

*   **Inventory users** (`stock.group_stock_user`) keep their normal Odoo
    rights. The scanner adds nothing to them.
*   **Barcode operators** (`stock_barcode_ce.group_barcode_operator`) have
    read-only access to the stock models. The scanner checks that the operator
    can read the transfer (access rights and record rules), then runs the scan
    engine with `sudo()`. The real user is kept on `create_uid`, on the scan
    events and in the scan log.

    Because the engine runs with elevated rights, **the operator role is meant
    for trusted warehouse staff of your own company**. Do not grant it to
    portal users, customers, suppliers or other untrusted parties.
*   **Barcode supervisors** may override scan rules, apply inventory counts,
    scrap products and confirm expired lots.
*   **Print agents** authenticate to two public HTTP endpoints
    (`/barcode_label/agent/poll` and `/barcode_label/agent/ack`) with a random
    token. Anyone who has the token can read the queued label data of that
    agent and mark its jobs as done. Treat the token like a password: keep it
    out of shell history and scripts that others can read, use HTTPS, and
    regenerate it from the agent form if it leaks.
*   **Bus notifications** between scanners carry record ids and the user name
    only, never quantities or product data.

## Scope

In scope: the seven modules in this repository, the print agent in
`stock_barcode_print_ce/tools/`, and the deployment scripts.

Out of scope: vulnerabilities in Odoo itself (report those to
[Odoo](https://www.odoo.com/security-report)), and problems that require
administrator rights on the Odoo database or shell access to the server.
