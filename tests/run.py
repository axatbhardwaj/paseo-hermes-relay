#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


MINIMUM_TESTS = 73
TEST_ROOT = Path(__file__).resolve().parent


def main():
    suite = unittest.defaultTestLoader.discover(str(TEST_ROOT))
    count = suite.countTestCases()
    if count < MINIMUM_TESTS:
        print(
            f"expected at least {MINIMUM_TESTS} tests, discovered {count}",
            file=sys.stderr,
        )
        return 1
    print(f"Discovered {count} tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
