[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $UpdateArgs
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

& git -C $RepoRoot pull --ff-only
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Set-Location $RepoRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m skillforge update --root $RepoRoot @UpdateArgs
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 -m skillforge update --root $RepoRoot @UpdateArgs
} else {
    & python -m skillforge update --root $RepoRoot @UpdateArgs
}

exit $LASTEXITCODE
