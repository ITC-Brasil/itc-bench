#Requires -Version 7.4
<#
.SYNOPSIS
    Gera os dois pares de chaves da atualização do Bench (ADR-026): principal e reserva.

.DESCRIPTION
    ECDSA P-256. Cada chave privada sai em PKCS#8 cifrado (PBKDF2-SHA256 + AES-256-CBC, senha
    pedida aqui, nunca em argumento nem em arquivo) na pasta -Saida, que tem que ficar FORA do
    repositório. As chaves públicas (SubjectPublicKeyInfo em base64) vão para
    app/src/itc_bench/recursos/atualizacao/principal.pub e reserva.pub, que o responsável comita.
    Rode uma vez, na sua máquina. A reserva vai para guarda fora de linha (docs/BUILD.md).

.EXAMPLE
    pwsh -File instalador/gerar-chaves-versao.ps1 -Saida <pasta fora do repositório>
#>
param(
    [Parameter(Mandatory)][string]$Saida,
    # Só para o CI (chave de teste descartável): senha já em SecureString, sem pergunta.
    [securestring]$Senha,
    # Pasta das públicas; padrão é a do pacote. O CI aponta para a árvore de trabalho do job.
    [string]$Publicas = (Join-Path $PSScriptRoot '..\app\src\itc_bench\recursos\atualizacao')
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
New-Item -ItemType Directory -Force $Saida | Out-Null
$saidaAbs = (Resolve-Path $Saida).Path
if ($saidaAbs.StartsWith($repo, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'A pasta das chaves privadas não pode ficar dentro do repositório.'
}
New-Item -ItemType Directory -Force $Publicas | Out-Null
$pbe = [Security.Cryptography.PbeParameters]::new(
    [Security.Cryptography.PbeEncryptionAlgorithm]::Aes256Cbc,
    [Security.Cryptography.HashAlgorithmName]::SHA256, 600000)

foreach ($nome in 'principal', 'reserva') {
    $privada = Join-Path $saidaAbs "$nome.key.pem"
    if (Test-Path $privada) { throw "Já existe $nome.key.pem em -Saida; não sobrescrevo chave." }
    $s = $Senha
    if (-not $s) {
        $s = Read-Host "Senha da chave $nome" -AsSecureString
        $c = Read-Host "Repita a senha da chave $nome" -AsSecureString
        if ([Net.NetworkCredential]::new('', $s).Password -cne [Net.NetworkCredential]::new('', $c).Password) {
            throw 'As senhas não conferem.'
        }
    }
    $texto = [Net.NetworkCredential]::new('', $s).Password
    if ($texto.Length -lt 16) { throw 'Use senha com 16 caracteres ou mais.' }
    $ec = [Security.Cryptography.ECDsa]::Create([Security.Cryptography.ECCurve+NamedCurves]::nistP256)
    try {
        Set-Content -LiteralPath $privada -Value $ec.ExportEncryptedPkcs8PrivateKeyPem($texto, $pbe) -Encoding ascii -NoNewline
        $pub = [Convert]::ToBase64String($ec.ExportSubjectPublicKeyInfo())
        Set-Content -LiteralPath (Join-Path $Publicas "$nome.pub") -Value $pub -Encoding ascii -NoNewline
    } finally { $ec.Dispose() }
    Write-Output "Chave $nome gerada. Pública em $nome.pub; privada em -Saida."
}
