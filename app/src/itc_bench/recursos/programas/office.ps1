# Office pré-instalado, Click-to-Run (ADR-063). $PRODUTOS vem fechada do código
# (desinstalar.OFFICE_PRE_INSTALADO). ITC_ACAO: ver | remover. ITC_NOMES: produtos, um por linha,
# conferidos de novo aqui. Só entradas de desinstalação cujo executável é o OfficeClickToRun.exe
# de Program Files; os argumentos são refeitos só com chave=valor conhecidas, mais o modo
# silencioso. Office fora da lista (corporativo, instalado pela etapa Programas) não é tocado.
$exe = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'Common Files\Microsoft Shared\ClickToRun\OfficeClickToRun.exe'
$raizes = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$permitidas = @('scenario', 'scenariosubtype', 'sourceplatform', 'productstoremove', 'culture', 'version.16')
$pedidos = @(if ($env:ITC_NOMES) { $env:ITC_NOMES -split "`n" | Where-Object { $_ } })
$achados = @()
if (Test-Path -LiteralPath $exe) {
    foreach ($k in @(Get-ItemProperty -Path $raizes -ErrorAction SilentlyContinue)) {
        $u = [string]$k.UninstallString
        $cabeca = '"' + $exe + '"'
        if (-not $u.StartsWith($cabeca, [StringComparison]::OrdinalIgnoreCase)) { continue }
        $valores = @{}
        foreach ($t in ($u.Substring($cabeca.Length).Trim() -split '\s+')) {
            if ($t -match '^([A-Za-z0-9.]+)=([A-Za-z0-9._-]+)$') { $valores[$matches[1].ToLower()] = $matches[2] }
        }
        $produto = ([string]$valores['productstoremove'] -split '\.')[0]
        if ($PRODUTOS -notcontains $produto) { continue }
        $achados += [pscustomobject]@{ produto = $produto; cultura = [string]$valores['culture']; valores = $valores }
    }
}
if ($env:ITC_ACAO -eq 'ver') {
    $saida = foreach ($a in $achados) { [pscustomobject]@{ produto = $a.produto; cultura = $a.cultura } }
    ConvertTo-Json -Compress -InputObject @($saida)
    return
}
if ($env:ITC_ACAO -ne 'remover') { throw 'acao invalida' }
foreach ($n in $pedidos) {
    if ($PRODUTOS -notcontains $n) { Write-Output ('ERRO|fora_da_lista|' + $n); continue }
    foreach ($a in @($achados | Where-Object produto -eq $n)) {
        $lista = @(foreach ($c in $permitidas) { if ($a.valores.ContainsKey($c)) { $c + '=' + $a.valores[$c] } })
        $lista += @('DisplayLevel=False', 'forceappshutdown=True')
        & $exe @lista
        if ($LASTEXITCODE -eq 0) { Write-Output ('OK|' + $n) } else { Write-Output ('ERRO|codigo_' + $LASTEXITCODE + '|' + $n) }
    }
}
