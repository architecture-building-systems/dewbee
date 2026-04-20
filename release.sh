#!/bin/bash
set -e

if [ -n "$(git status --porcelain)" ]; then
  echo "Staging release files..."
  git add -A
else
  echo "No changes detected. Nothing to release."
  exit 1
fi

VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
TAG="v$VERSION"

echo "Building package..."
python -m build

echo "Committing release..."
git commit -m "Release $TAG"

echo "Creating tag $TAG..."
git tag -a "$TAG" -m "Release $TAG"

echo "Pushing commit and tag..."
git push origin main --tags

echo ""
echo "Release prepared: $TAG"
echo "Now create the GitHub Release at:"
echo "https://github.com/architecture-building-systems/dewbee/releases/new?tag=$TAG"