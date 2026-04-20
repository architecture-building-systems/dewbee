$ErrorActionPreference = "Stop"

function Get-CurrentVersion {
    $pyproject = Get-Content "pyproject.toml" -Raw
    if ($pyproject -match 'version\s*=\s*"([^"]+)"') {
        return $matches[1]
    }
    throw "Could not find version in pyproject.toml"
}

Write-Host "Checking for release changes..."
$gitStatus = git status --porcelain
if (-not $gitStatus) {
    throw "No changes detected. Nothing to release."
}

$version = Get-CurrentVersion
$tag = "v$version"

Write-Host "Building package..."
python -m build

Write-Host "Staging files..."
git add -A

Write-Host "Committing release..."
git commit -m "Release $tag"

Write-Host "Creating tag $tag..."
git tag -a $tag -m "Release $tag"

Write-Host "Pushing commit and tag..."
git push origin main --tags

Write-Host ""
Write-Host "Release prepared: $tag"
Write-Host "Now create the GitHub Release at:"
Write-Host "https://github.com/architecture-building-systems/dewbee/releases/new?tag=$tag"