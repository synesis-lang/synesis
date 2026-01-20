#!/bin/bash
# Quick build and validation script for Synesis

set -e

echo "=========================================="
echo "Synesis Build and Validation"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Clean previous builds
echo -e "${YELLOW}[1/6] Cleaning previous builds...${NC}"
rm -rf dist/ build/ *.egg-info
echo -e "${GREEN}✓ Clean complete${NC}"
echo ""

# Step 2: Run tests
echo -e "${YELLOW}[2/6] Running tests...${NC}"
if pytest -q; then
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo -e "${RED}✗ Tests failed. Fix errors before building.${NC}"
    exit 1
fi
echo ""

# Step 3: Build package
echo -e "${YELLOW}[3/6] Building package...${NC}"
if python -m build; then
    echo -e "${GREEN}✓ Build successful${NC}"
else
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi
echo ""

# Step 4: Check distribution
echo -e "${YELLOW}[4/6] Validating distribution with twine...${NC}"
if twine check dist/*; then
    echo -e "${GREEN}✓ Distribution valid${NC}"
else
    echo -e "${RED}✗ Distribution validation failed${NC}"
    exit 1
fi
echo ""

# Step 5: List contents
echo -e "${YELLOW}[5/6] Package contents:${NC}"
ls -lh dist/
echo ""

# Step 6: Summary
echo -e "${YELLOW}[6/6] Summary${NC}"
echo "----------------------------------------"
echo -e "${GREEN}✓ Package ready for publication!${NC}"
echo ""
echo "Next steps:"
echo "  • TestPyPI: twine upload --repository testpypi dist/*"
echo "  • PyPI:     twine upload dist/*"
echo ""
echo "Or run the pre-publication checklist:"
echo "  python check_ready.py"
echo "=========================================="
