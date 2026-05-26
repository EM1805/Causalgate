# IP and License Disclosure

This document is a practical disclosure template for a sale of CausalGate. It is not legal advice.

## Ownership statement to complete before sale

The seller should complete this statement before closing:

> I represent that I own or have the right to transfer the source code, documentation, product copy, examples, and sales materials included in this CausalGate package, except for third-party dependencies listed below.

## Main package license model

CausalGate is intended to be sold as source-available commercial software.

Recommended sale model:

- source code visible to buyer
- full IP assignment or exclusive commercial rights transferred in sale
- buyer may choose future licensing model after transfer

## Third-party Python dependencies

Declared direct dependencies in `pyproject.toml`:

- NumPy
- pandas
- PyYAML
- FastAPI, optional server extra
- Uvicorn, optional server extra
- pytest, optional test extra

The buyer should run an independent license audit before commercial deployment.

## GPL / copyleft caution

Before selling or deploying commercially, confirm that no GPL or other copyleft code was copied into the proprietary/source-available parts of the package.

The package includes custom PCMCI-style, SCM, identification, estimation, and runtime components. A buyer should verify originality and third-party-license compatibility during diligence.

## Suggested diligence tools

- `pip-licenses`
- GitHub dependency graph
- GitHub code search
- `scancode-toolkit`
- legal review by open-source counsel
