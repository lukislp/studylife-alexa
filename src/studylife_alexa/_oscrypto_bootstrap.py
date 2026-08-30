"""Works around oscrypto (a transitive dependency of ask-sdk-webservice-support's
certificate-chain verifier, via certvalidator) failing to auto-detect OpenSSL's version
on distros whose libcrypto.so.3/libssl.so.3 (OpenSSL 3.x) version string its regex
doesn't recognize - raises oscrypto.errors.LibraryNotFoundError the first time any
crypto operation actually runs (lazily, not at `import oscrypto` itself - the detection
lives deep in oscrypto._openssl._libcrypto, only touched once the "openssl" backend is
actually used).

oscrypto.use_openssl() sidesteps the auto-detection entirely by taking explicit library
paths, but per its own docstring it "must be called before any oscrypto submodules are
imported" - so this has to run before ask_sdk_webservice_support (which pulls in
certvalidator -> oscrypto) is imported anywhere in the process. Hence its own module,
imported first thing in main.py, rather than being handled at the call site that
actually needs verification.

Resolves the real .so paths via `ldconfig -p` rather than guessing a hardcoded
per-distro/per-arch path (ctypes.util.find_library only returns a bare soname on Linux,
not an absolute path oscrypto can os.path.exists() check).
"""

from __future__ import annotations

import subprocess
import sys


def _resolve_via_ldconfig(soname_fragment: str) -> str | None:
    try:
        result = subprocess.run(
            ["/sbin/ldconfig", "-p"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"studylife_alexa oscrypto bootstrap: ldconfig failed: {exc!r}", file=sys.stderr)
        return None

    for line in result.stdout.splitlines():
        if soname_fragment in line and "=>" in line:
            return line.split("=>", 1)[1].strip()

    print(
        f"studylife_alexa oscrypto bootstrap: no ldconfig entry matched {soname_fragment!r}",
        file=sys.stderr,
    )
    return None


def apply() -> None:
    if sys.platform != "linux":
        # macOS/Windows use their native crypto APIs (Security.framework / CryptoAPI),
        # not the OpenSSL binding - oscrypto's own detection doesn't apply there.
        return

    libcrypto_path = _resolve_via_ldconfig("libcrypto.so")
    libssl_path = _resolve_via_ldconfig("libssl.so")
    if libcrypto_path is None or libssl_path is None:
        # Fall through to oscrypto's own detection - better an informative
        # LibraryNotFoundError from oscrypto itself than a silent skip here.
        return

    import oscrypto

    oscrypto.use_openssl(libcrypto_path, libssl_path)
