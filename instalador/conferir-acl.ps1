# ACL da pasta de instalação (ADR-025): além de SYSTEM, Administradores, TrustedInstaller e
# CREATOR OWNER, ninguém grava; sem ponto de reparse. Usado por testar.ps1 e
# testar-atualizacao.ps1. Sai 0 se passou, 1 se não.
param([Parameter(Mandatory = $true)][string]$Pasta)
$ErrorActionPreference = 'Stop'
$confiaveis = @('S-1-5-18', 'S-1-5-32-544', 'S-1-3-0',
    'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
# Mesma máscara de nucleo/instalacao.py: gravar, anexar, EA, apagar filho, atributos, DELETE,
# WRITE_DAC, WRITE_OWNER, GENERIC_ALL e GENERIC_WRITE (os genéricos aparecem como número).
$escrita = 0x2 -bor 0x4 -bor 0x10 -bor 0x40 -bor 0x100 -bor 0x10000 -bor 0x40000 -bor 0x80000 -bor 0x10000000 -bor 0x40000000
$itens = @((Get-Item (Split-Path $Pasta)), (Get-Item $Pasta)) + @(Get-ChildItem $Pasta -Recurse -Force)
$abertos = foreach ($item in $itens) {
    # Regras já em SID: SIDs de capacidade (ALL APPLICATION PACKAGES etc.) não traduzem para nome.
    $regras = (Get-Acl $item.FullName).GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
    foreach ($ace in $regras) {
        $sid = $ace.IdentityReference.Value
        if ($ace.AccessControlType -eq 'Allow' -and $sid -notin $confiaveis -and
            (([int64][int]$ace.FileSystemRights) -band $escrita)) { "$($item.Name): $sid" }
    }
}
$reparse = $itens | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
Write-Host "ACL conferida em $($itens.Count) itens; com escrita de terceiros: $(@($abertos).Count); reparse: $(@($reparse).Count)"
$abertos | Select-Object -First 5 | ForEach-Object { Write-Host "      $_" }
exit ([int]([bool]$abertos -or [bool]$reparse))
