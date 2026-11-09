# Mutex do Bench x usuário comum (ADR-026), no runner do CI (máquina descartável).
# Cria um usuário comum temporário (senha aleatória, nunca impressa) que segura o mutex -Nome e,
# enquanto ele segura, roda o bloco -Instalar como administrador. Sai 0 se o usuário comum criou
# o mutex E o bloco devolveu $true (o instalador não travou). Sem -Instalar, só mede e sai 0.
param(
    [string]$Nome = 'Global\ITCBenchProva',
    [scriptblock]$Instalar
)
$ErrorActionPreference = 'Stop'
$usuario = 'itcprova'
$bytes = [byte[]]::new(24); [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$senha = ConvertTo-SecureString ([Convert]::ToBase64String($bytes) + 'a1!') -AsPlainText -Force
New-LocalUser -Name $usuario -Password $senha -AccountNeverExpires | Out-Null
$codigoSaida = 1
try {
    $cred = [pscredential]::new("$env:COMPUTERNAME\$usuario", $senha)
    $marca = Join-Path $env:PUBLIC 'itcprova.txt'
    Remove-Item $marca -ErrorAction SilentlyContinue
    $codigo = @"
`$criado = `$false
try { `$m = [Threading.Mutex]::new(`$false, '$Nome', [ref]`$criado); "criado=`$criado" | Set-Content '$marca' }
catch { "erro=`$(`$_.Exception.GetType().Name)" | Set-Content '$marca' }
Start-Sleep 120
"@
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($codigo))
    $p = Start-Process powershell.exe -Credential $cred -ArgumentList '-NoProfile', '-EncodedCommand', $enc -PassThru -WindowStyle Hidden
    for ($i = 0; $i -lt 30 -and -not (Test-Path $marca); $i++) { Start-Sleep 1 }
    $resultado = if (Test-Path $marca) { Get-Content $marca } else { 'sem resposta' }
    Write-Output "usuario comum: $resultado"
    $criou = $resultado -eq 'criado=True'
    if ($Instalar) {
        $passou = & $Instalar
        Write-Output "instalador com o mutex do usuario comum: $(if ($passou) { 'passou' } else { 'travou' })"
        if ($criou -and $passou) { $codigoSaida = 0 }
    } else {
        $codigoSaida = 0
    }
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
} finally {
    Remove-LocalUser -Name $usuario
}
exit $codigoSaida
