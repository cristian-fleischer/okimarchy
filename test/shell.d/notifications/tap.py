"""Run the notification helper unit tests and report them in base-test.sh's TAP lines.

Every test prints `ok - ...`; a skipped one ends in ` # SKIP` with its reason
before the marker, so ./test/shell lists the file as having skipped checks.
Failures print their traceback to stderr and `not ok - ...`, and the run
exits non-zero after every test has had its turn.
"""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class TapResult(unittest.TestResult):
  def __init__(self):
    super().__init__()
    self.failed = 0

  @staticmethod
  def name(test):
    return "notification helpers: " + test.id().removeprefix("test_")

  def addSuccess(self, test):
    super().addSuccess(test)
    print("ok - " + self.name(test), flush=True)

  def addSkip(self, test, reason):
    super().addSkip(test, reason)
    print("ok - %s (%s) # SKIP" % (self.name(test), reason), flush=True)

  def report(self, test, err):
    self.failed += 1
    sys.stderr.write(self._exc_info_to_string(err, test))
    print("not ok - " + self.name(test), flush=True)

  def addFailure(self, test, err):
    super().addFailure(test, err)
    self.report(test, err)

  def addError(self, test, err):
    super().addError(test, err)
    self.report(test, err)

  def addSubTest(self, test, subtest, err):
    super().addSubTest(test, subtest, err)
    if err is not None:
      self.report(subtest, err)

  def addUnexpectedSuccess(self, test):
    super().addUnexpectedSuccess(test)
    self.failed += 1
    print("not ok - %s (unexpected success)" % self.name(test), flush=True)


def main():
  suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py", top_level_dir=str(HERE))
  result = TapResult()
  suite.run(result)
  if result.testsRun == 0:
    print("not ok - notification helper tests were found")
    return 1
  return 1 if result.failed else 0


if __name__ == "__main__":
  sys.exit(main())
