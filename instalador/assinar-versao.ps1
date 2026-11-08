#Requires -Version 7.4
<#
.SYNOPSIS
    Gera e assina o manifesto de uma versão do Bench (ADR-026) para a CLI app.bench_versao.

.DESCRIPTION
    Lê o instalador baixado do CI, confere o SHA-256 com o SHA256SUMS do mesmo run, monta o
    manifesto (JSON UTF-8 sem BOM, campos fixos) e assina os bytes exatos com ECDSA P-256 /
    SHA-256, em IEEE P1363 (r||s, 64 bytes), o formato que o Bench confere pela CNG.
    Saída em -Saida: manifesto.json e manifesto.sig. A chave privada não sai da sua máquina.

.EXAMPLE
    pwsh -File instalador/assinar-versao.ps1 -Instalador itc-bench-0.16.0-setup.exe `
        -Sha256Sums SHA256SUMS -Minima 0.15.0 -Notas "Atualização automática." `
        -Chave <pasta fora do repositório>\principal.key.pem -Saida <pasta>
#>
param(
    [Parameter(Mandatory)][string]$Instalador,
    [Parameter(Mandatory)][string]$Sha256Sums,
    [Parameter(Mandatory)][string]$Minima,
    [Parameter(Mandatory)][string]$Notas,
    [Parameter(Mandatory)][string]$Chave,
    [Parameter(Mandatory)][string]$Saida,
    [securestring]$Senha  # só para o CI; sem ela, a senha é pedida
)
$ErrorActionPreference = 'Stop'
$nome = Split-Path $Instalador -Leaf
if ($nome -notmatch '^itc-bench-((0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2}))-setup\.exe$') {
    throw 'Nome do instalador fora do padrão itc-bench-X.Y.Z-setup.exe.'
}
$versao = $Matches[1]
if ($Minima -notmatch '^(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})$') { throw 'Mínima fora de X.Y.Z.' }
if ([version]$Minima -gt [version]$versao) { throw 'Mínima acima da versão.' }
if ($Notas.Length -gt 500 -or $Notas -match '[\x00-\x09\x0B-\x1F]') { throw 'Notas: até 500 caracteres, texto puro.' }
$sha = (Get-FileHash -LiteralPath $Instalador -Algorithm SHA256).Hash.ToLowerInvariant()
$linha = Get-Content -LiteralPath $Sha256Sums | Where-Object { $_ -match "^([0-9a-fA-F]{64})\s+\*?$([regex]::Escape($nome))$" }
if (-not $linha -or $Matches[1].ToLowerInvariant() -ne $sha) { throw 'O instalador não confere com o SHA256SUMS.' }
$tamanho = (Get-Item -LiteralPath $Instalador).Length

# Ordem e campos iguais aos de api/app/bench_versao.py e servicos/atualizacao.py.
$manifesto = [ordered]@{
    produto      = 'itc-bench'
    app_id       = '{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}'
    versao       = $versao
    minima       = $Minima
    sha256       = $sha
    tamanho      = $tamanho
    notas        = $Notas
    publicado_em = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
}
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($manifesto | ConvertTo-Json -Compress))
$s = if ($Senha) { $Senha } else { Read-Host 'Senha da chave' -AsSecureString }
$ec = [Security.Cryptography.ECDsa]::Create()
try {
    $ec.ImportFromEncryptedPem((Get-Content -LiteralPath $Chave -Raw), [Net.NetworkCredential]::new('', $s).Password)
    if ($ec.KeySize -ne 256) { throw 'A chave não é P-256.' }
    $assinatura = $ec.SignData($bytes, [Security.Cryptography.HashAlgorithmName]::SHA256,
        [Security.Cryptography.DSASignatureFormat]::IeeeP1363FixedFieldConcatenation)
    if (-not $ec.VerifyData($bytes, $assinatura, [Security.Cryptography.HashAlgorithmName]::SHA256,
            [Security.Cryptography.DSASignatureFormat]::IeeeP1363FixedFieldConcatenation)) { throw 'Assinatura não confere.' }
} finally { $ec.Dispose() }
New-Item -ItemType Directory -Force $Saida | Out-Null
[IO.File]::WriteAllBytes((Join-Path $Saida 'manifesto.json'), $bytes)
[IO.File]::WriteAllBytes((Join-Path $Saida 'manifesto.sig'), $assinatura)
Write-Output "Versão $versao assinada (sha256 $($sha.Substring(0, 12))…, $tamanho bytes)."
