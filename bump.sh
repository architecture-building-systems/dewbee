#!/bin/bash
set -e

BUMP_TYPE=${1:-patch}

if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean. Commit or stash changes first."
  exit 1
fi

CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
echo "Current version: $CURRENT_VERSION"

MAJOR=$(echo "$CURRENT_VERSION" | cut -d. -f1)
MINOR=$(echo "$CURRENT_VERSION" | cut -d. -f2)
PATCH=$(echo "$CURRENT_VERSION" | cut -d. -f3)

if [ "$BUMP_TYPE" = "major" ]; then
  NEW_VERSION="$((MAJOR + 1)).0.0"
elif [ "$BUMP_TYPE" = "minor" ]; then
  NEW_VERSION="$MAJOR.$((MINOR + 1)).0"
elif [ "$BUMP_TYPE" = "patch" ]; then
  NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
else
  echo "ERROR: Invalid bump type '$BUMP_TYPE'. Use patch, minor, or major."
  exit 1
fi

echo "New version: $NEW_VERSION"

sed -i '' "s/version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml
sed -i '' "s/__version__ = \"$CURRENT_VERSION\"/__version__ = \"$NEW_VERSION\"/" dewbee/__init__.py

python -m build

echo ""
echo "Version bumped to $NEW_VERSION"
echo "Now open Grasshopper, run your component update/save script, then run ./release.sh"