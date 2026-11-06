# Localiza o winget.exe pelo pacote DesktopAppInstaller (ADR-020). Só leitura; devolve JSON.
$p = Get-AppxPackage -Name Microsoft.DesktopAppInstaller -ErrorAction SilentlyContinue |
    Sort-Object Version -Descending | Select-Object -First 1
if (-not $p) {
    $p = Get-AppxPackage -AllUsers -Name Microsoft.DesktopAppInstaller -ErrorAction SilentlyContinue |
        Sort-Object Version -Descending | Select-Object -First 1
}
if (-not $p) { '{}'; return }
$exe = Join-Path $p.InstallLocation 'winget.exe'
$valida = $false
$microsoft = $false
if (Test-Path -LiteralPath $exe -PathType Leaf) {
    $a = Get-AuthenticodeSignature -LiteralPath $exe
    $valida = $a.Status -eq 'Valid'
    $microsoft = [bool]($a.SignerCertificate -and $a.SignerCertificate.Subject -match '(^|, )O=Microsoft Corporation(,|$)')
}
[pscustomobject]@{
    caminho   = $exe
    tipo      = [string]$p.SignatureKind
    valida    = $valida
    microsoft = $microsoft
} | ConvertTo-Json -Compress
