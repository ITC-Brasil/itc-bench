# Gera o EXE (PyInstaller) e o instalador (Inno Setup) do ITC Bench (ADR-025).
# Uso, da raiz do repositório:  .\instalador\build.ps1 -Iscc C:\caminho\ISCC.exe
# Artefato distribuível só pelo CI: o build local embute caminhos desta máquina (docs/BUILD.md).
param(
    [Parameter(Mandatory = $true)][string]$Iscc
)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$app = Join-Path $raiz 'app'

$init = Get-Content (Join-Path $app 'src\itc_bench\__init__.py') -Raw
if ($init -notmatch '__version__ = "(\d+\.\d+\.\d+)"') { throw 'Versão não encontrada em __init__.py' }
$versao = $Matches[1]
Write-Host "ITC Bench $versao"

Push-Location $app
try {
    & uv sync --frozen --group build
    if ($LASTEXITCODE) { throw "uv sync falhou ($LASTEXITCODE)" }
    & uv run --frozen --group build pyinstaller --noconfirm --clean --distpath dist --workpath build empacotamento\itc-bench.spec
    if ($LASTEXITCODE) { throw "PyInstaller falhou ($LASTEXITCODE)" }
} finally { Pop-Location }

& $Iscc /Q "/DAppVersion=$versao" (Join-Path $PSScriptRoot 'itc-bench.iss')
if ($LASTEXITCODE) { throw "ISCC falhou ($LASTEXITCODE)" }

$setup = Join-Path $app "dist\itc-bench-$versao-setup.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  itc-bench-$versao-setup.exe" | Set-Content (Join-Path $app 'dist\SHA256SUMS') -Encoding ascii
Write-Host "$setup`n$hash"
