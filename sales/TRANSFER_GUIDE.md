# CausalGate Transfer Guide

This guide is for a complete asset sale of CausalGate.

## Assets to transfer

- Full source-code repository
- ZIP source archive
- Product documentation
- Static landing page in `site/index.html`
- CLI, FastAPI server, Dockerfile, examples, and tests
- Commercial-license templates
- Marketplace listing copy
- Any domain name, social accounts, demo hosting, analytics, or waitlist if created later

## Technical handover

1. Share the repository with the buyer.
2. Transfer ownership of the repository or export the full Git history.
3. Provide the current release ZIP.
4. Provide setup instructions:

```bash
python -m pip install -e .[server,test]
causalgate demo --out-dir out/demo
causalgate api --host 0.0.0.0 --port 8000
```

5. Point the buyer to these files:

```text
README.md
LICENSE.md
COMMERCIAL-LICENSE.md
docs/API_SERVER.md
docs/DEMO.md
docs/CAUSAL_AUTHORITY.md
sales/BUYER_DUE_DILIGENCE.md
sales/IP_AND_LICENSE_DISCLOSURE.md
```

## Suggested verification by buyer

```bash
python -m compileall .
python -m pytest tests/test_causal_authority_step3.py tests/test_product_api_server_step5.py
causalgate demo --out-dir out/demo
```

## IP assignment items

A complete sale should include a signed document stating that the seller transfers all rights they own in:

- source code
- documentation
- product name and brand assets, if any
- commercial-license templates
- landing-page copy
- examples and demo materials

This guide is not legal advice. Use a lawyer for the final agreement.

## Buyer support window

Suggested handover support:

- 7 days for a low-price sale
- 14 days for a mid-price sale
- 30 days for a premium sale

Support should cover setup, file transfer, and codebase orientation, not new feature development.
