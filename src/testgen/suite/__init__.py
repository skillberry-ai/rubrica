"""Files copied verbatim into every emitted task package.

verify.py and test.sh execute inside the task container -- a bare ubi9 image
with no third-party packages and no network -- so they are stdlib-only and must
never import testgen. They live inside the package so the tests exercise the
same bytes emit copies, which is the only way the tested file and the executed
file cannot drift apart.
"""
