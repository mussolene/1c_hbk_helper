#!/usr/bin/env python3
"""Parse FastCode templates into snippets JSON. Delegates to onec_help parse-fastcode.

Usage: python -m onec_help parse-fastcode [--out PATH] [--pages 1-51]
       python scripts/parse_fastcode.py [--out PATH] [--pages 1-51]
"""

import sys

if __name__ == "__main__":
    sys.argv = ["onec_help", "parse-fastcode"] + sys.argv[1:]
    from onec_help.cli import main

    sys.exit(main())
