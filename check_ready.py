#!/usr/bin/env python3
"""
check_ready.py - Pre-publication validation script

Validates that the Synesis package is ready for publication to PyPI/TestPyPI.
Checks for common issues and provides actionable feedback.

Usage:
    python check_ready.py
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Tuple

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


class PreflightCheck:
    """Run pre-publication validation checks."""

    def __init__(self):
        self.root = Path(__file__).parent
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def check(self, name: str, condition: bool, error_msg: str = "", warning: bool = False) -> bool:
        """Run a single check and display result."""
        if condition:
            print(f"{GREEN}✓{RESET} {name}")
            if not warning:
                self.passed += 1
            return True
        else:
            if warning:
                print(f"{YELLOW}⚠{RESET} {name}")
                if error_msg:
                    print(f"  {YELLOW}{error_msg}{RESET}")
                self.warnings += 1
            else:
                print(f"{RED}✗{RESET} {name}")
                if error_msg:
                    print(f"  {RED}{error_msg}{RESET}")
                self.failed += 1
            return False

    def check_file_exists(self, filepath: str, required: bool = True) -> bool:
        """Check if a file exists."""
        path = self.root / filepath
        exists = path.exists()
        self.check(
            f"File exists: {filepath}",
            exists,
            f"Missing file: {filepath}" if required else "",
            warning=not required
        )
        return exists

    def check_file_not_empty(self, filepath: str) -> bool:
        """Check if a file has content."""
        path = self.root / filepath
        if not path.exists():
            return False

        size = path.stat().st_size
        self.check(
            f"File not empty: {filepath}",
            size > 100,
            f"File is too small ({size} bytes), may be incomplete"
        )
        return size > 100

    def run_command(self, cmd: List[str]) -> Tuple[bool, str]:
        """Run a shell command and return success status and output."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.root
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def check_tests_pass(self) -> bool:
        """Run pytest and check if all tests pass."""
        print(f"\n{BLUE}Running tests...{RESET}")
        success, output = self.run_command(["pytest", "-q"])

        if success:
            self.check("All tests pass", True)
            return True
        else:
            self.check(
                "All tests pass",
                False,
                "Some tests failed. Run 'pytest' for details."
            )
            return False

    def check_build_succeeds(self) -> bool:
        """Check if package builds successfully."""
        print(f"\n{BLUE}Building package...{RESET}")
        success, output = self.run_command([sys.executable, "-m", "build", "--outdir", "dist_test"])

        if success:
            self.check("Package builds successfully", True)
            # Clean up test build
            import shutil
            shutil.rmtree(self.root / "dist_test", ignore_errors=True)
            return True
        else:
            self.check(
                "Package builds successfully",
                False,
                "Build failed. Install 'build' package: pip install build"
            )
            return False

    def check_twine_validation(self) -> bool:
        """Check if distribution passes twine validation."""
        dist_dir = self.root / "dist"
        if not dist_dir.exists() or not list(dist_dir.glob("*.tar.gz")):
            self.check(
                "Distribution files validated",
                False,
                "No distribution files found. Run: python -m build",
                warning=True
            )
            return False

        print(f"\n{BLUE}Validating with twine...{RESET}")
        success, output = self.run_command(["twine", "check", "dist/*"])

        if success:
            self.check("Distribution passes twine check", True)
            return True
        else:
            self.check(
                "Distribution passes twine check",
                False,
                "Twine validation failed. Install twine: pip install twine"
            )
            return False

    def check_version_format(self) -> bool:
        """Check if version in pyproject.toml follows semantic versioning."""
        import re
        pyproject = self.root / "pyproject.toml"

        if not pyproject.exists():
            return False

        content = pyproject.read_text()
        match = re.search(r'version\s*=\s*"([^"]+)"', content)

        if match:
            version = match.group(1)
            # Check semantic versioning format
            is_valid = bool(re.match(r'^\d+\.\d+\.\d+(-[a-z0-9]+)?$', version))
            self.check(
                f"Version format valid: {version}",
                is_valid,
                f"Version '{version}' doesn't follow SemVer (e.g., 0.1.0)"
            )
            return is_valid
        else:
            self.check("Version found in pyproject.toml", False)
            return False

    def check_no_dev_version(self) -> bool:
        """Warn if version contains -dev suffix."""
        pyproject = self.root / "pyproject.toml"
        content = pyproject.read_text()

        has_dev = "-dev" in content or "dev" in content.lower()
        self.check(
            "Version is not a dev version",
            not has_dev,
            "Version contains 'dev' - consider removing for release",
            warning=True
        )
        return not has_dev

    def run_all_checks(self):
        """Run all pre-publication checks."""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}Synesis Pre-Publication Checklist{RESET}")
        print(f"{BLUE}{'='*60}{RESET}\n")

        # Essential files
        print(f"{BLUE}Checking essential files...{RESET}")
        self.check_file_exists("LICENSE")
        self.check_file_exists("README.md")
        self.check_file_exists("CHANGELOG.md")
        self.check_file_exists("pyproject.toml")
        self.check_file_exists("MANIFEST.in")
        self.check_file_exists(".gitignore")

        # File content checks
        print(f"\n{BLUE}Checking file contents...{RESET}")
        self.check_file_not_empty("README.md")
        self.check_file_not_empty("CHANGELOG.md")
        self.check_file_not_empty("LICENSE")

        # Optional but recommended files
        print(f"\n{BLUE}Checking optional files...{RESET}")
        self.check_file_exists("CONTRIBUTING.md", required=False)
        self.check_file_exists(".github/workflows/ci.yml", required=False)

        # Package structure
        print(f"\n{BLUE}Checking package structure...{RESET}")
        self.check_file_exists("synesis/__init__.py")
        self.check_file_exists("synesis/cli.py")
        self.check_file_exists("synesis/compiler.py")
        self.check_file_exists("synesis/grammar/synesis.lark")

        # Version checks
        print(f"\n{BLUE}Checking version...{RESET}")
        self.check_version_format()
        self.check_no_dev_version()

        # Tests
        self.check_tests_pass()

        # Build
        self.check_build_succeeds()

        # Twine validation
        self.check_twine_validation()

        # Summary
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}Summary{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")
        print(f"{GREEN}Passed: {self.passed}{RESET}")
        print(f"{RED}Failed: {self.failed}{RESET}")
        print(f"{YELLOW}Warnings: {self.warnings}{RESET}")

        if self.failed == 0:
            print(f"\n{GREEN}✓ All critical checks passed!{RESET}")
            print(f"{GREEN}Package is ready for publication.{RESET}\n")
            print("Next steps:")
            print("  1. Build: python -m build")
            print("  2. Test upload: twine upload --repository testpypi dist/*")
            print("  3. Production: twine upload dist/*")
            return True
        else:
            print(f"\n{RED}✗ Some checks failed.{RESET}")
            print(f"{RED}Please fix the issues above before publishing.{RESET}\n")
            return False


def main():
    """Main entry point."""
    checker = PreflightCheck()
    success = checker.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
