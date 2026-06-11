"""Allow ``python -m cloud_bmt`` (CI gate preflight, local ``just gate-verify``)."""

from cloud_bmt.driver import main

if __name__ == "__main__":
    main()
