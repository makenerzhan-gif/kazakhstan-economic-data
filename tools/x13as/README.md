# X-13ARIMA-SEATS (US Census Bureau), vendored

`x13as_ascii` is the official Linux build of X-13ARIMA-SEATS **Version 1.1 Build 62**, ASCII-output
variant (the one statsmodels and `scripts/lib/x13.py` drive), unchanged.

| | |
|---|---|
| Source | https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/program-archives/x13as_ascii-v1-1-b62.tar.gz (member `x13as/x13as_ascii`) |
| Archive listing date | 2025-07-10 (latest Linux build as of 2026-09-27; previous: b61, 2024-07-09) |
| Tarball sha256 | `a91d37bb2fef46237e1eadd7d9b4f1c00a422d58f6b286c9bfe485289e8ac6f5` (3 837 943 bytes) |
| Binary sha256 | `72e4735dd8d96974fbfe2d80d38a83ee1cca5c8b6fa3dfd9a89aa952a1cb4a15` (4 812 584 bytes) |
| Binary | ELF 64-bit x86-64, statically linked (runs on any x86-64 Linux, no libraries) |
| Licence | Work of the US Government -- public domain |
| Documentation | https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/documentation/ (docX13AS.pdf, in the tarball too) |

Stored with git LFS. A checkout without LFS gets a text pointer instead of the program;
`scripts/lib/x13.py` then skips it and, where asked to (`ensure_binary(download=True)`, as
`scripts/build_model_data.py` does), downloads the same tarball into
`~/.cache/kazakhstan-economic-data/x13as/` (or `$X13_CACHE`) and checks both sums above.
`$X13PATH` (the binary or its directory) overrides everything, e.g. for macOS or Windows
builds, which are not vendored.

To upgrade: download the new `x13as_ascii-v*-b*.tar.gz`, run `tests/test_x13.py` and
`scripts/build_model_data.py` against it via `X13PATH`, then replace this file and update
`X13_URL`, `X13_TARBALL_SHA256`, `X13_BINARY_SHA256` and `X13_VERSION` in `scripts/lib/x13.py`.
