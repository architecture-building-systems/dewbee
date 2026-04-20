param(
    [ValidateSet("patch", "minor", "major")]
    [string]$BumpType = "patch"
)

$ErrorActionPreference = "Stop"

function Get-CurrentVersion {
    $pyproject = Get-Content "pyproject.toml" -Raw
    if ($pyproject -match 'version\s*=\s*"([^"]+)"') {
        return $matches[1]
    }
    throw "Could not find version in pyproject.toml"
}

function Get-NewVersion($currentVersion, $bumpType) {
    $parts = $currentVersion.Split(".")
    if ($parts.Length -ne 3) {
        throw "Version '$currentVersion' is not in MAJOR.MINOR.PATCH format"
    }

    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    $patch = [int]$parts[2]

    switch ($bumpType) {
        "major" { return "$($major + 1).0.0" }
        "minor" { return "$major.$($minor + 1).0" }
        "patch" { return "$major.$minor.$($patch + 1)" }
        default { throw "Invalid bump type: $bumpType" }
    }
}

function Replace-InFile($path, $oldVersion, $newVersion, $patternTemplate) {
    $content = Get-Content $path -Raw
    $pattern = $patternTemplate.Replace("{VERSION}", [regex]::Escape($oldVersion))
    $newContent = [regex]::Replace($content, $pattern, {
        param($m)
        $m.Value.Replace($oldVersion, $newVersion)
    }, 1)

    if ($newContent -eq $content) {
        throw "Failed to update version in $path"
    }

    [System.IO.File]::WriteAllText((Resolve-Path $path), $newContent, (New-Object System.Text.UTF8Encoding($false)))
}

Write-Host "Checking git status..."
$gitStatus = git status --porcelain
if ($gitStatus) {
    throw "Working tree is not clean. Commit or stash changes first."
}

$currentVersion = Get-CurrentVersion
$newVersion = Get-NewVersion $currentVersion $BumpType

Write-Host "Current version: $currentVersion"
Write-Host "New version: $newVersion"

Replace-InFile "pyproject.toml" $currentVersion $newVersion 'version\s*=\s*"{VERSION}"'
Replace-InFile "dewbee\__init__.py" $currentVersion $newVersion '__version__\s*=\s*"{VERSION}"'

Write-Host "Building package..."
python -m build

Write-Host ""
Write-Host "Version bumped to $newVersion"
Write-Host "Now open Grasshopper, run your component update/save script, then run release.ps1"