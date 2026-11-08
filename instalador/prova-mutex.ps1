# Prova do ajuste 1 do Módulo 16: um usuário comum cria Global\ITCBench? (CI, runner descartável)
# Cria um usuário comum temporário com senha aleatória (nunca impressa), abre como ele um processo
# que segura o mutex e, como administrador, lê o dono do mutex. Sai 0 sempre que conseguir medir;
# o resultado vai para o log do job.
$ErrorActionPreference = 'Stop'
$nome = 'Global\ITCBenchProva'
$usuario = 'itcprova'
$bytes = [byte[]]::new(24); [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$senha = ConvertTo-SecureString ([Convert]::ToBase64String($bytes) + 'a1!') -AsPlainText -Force
New-LocalUser -Name $usuario -Password $senha -AccountNeverExpires | Out-Null
try {
    $cred = [pscredential]::new("$env:COMPUTERNAME\$usuario", $senha)
    $marca = Join-Path $env:PUBLIC 'itcprova.txt'
    Remove-Item $marca -ErrorAction SilentlyContinue
    $codigo = @"
`$criado = `$false
try { `$m = [Threading.Mutex]::new(`$false, '$nome', [ref]`$criado); "criado=`$criado" | Set-Content '$marca' }
catch { "erro=`$(`$_.Exception.GetType().Name)" | Set-Content '$marca' }
Start-Sleep 40
"@
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($codigo))
    $p = Start-Process powershell.exe -Credential $cred -ArgumentList '-NoProfile', '-EncodedCommand', $enc -PassThru -WindowStyle Hidden
    for ($i = 0; $i -lt 30 -and -not (Test-Path $marca); $i++) { Start-Sleep 1 }
    $resultado = if (Test-Path $marca) { Get-Content $marca } else { 'sem resposta' }
    Write-Output "usuario comum: $resultado"
    # Dono e grupos do token do usuário comum, para o relatório (sem nome de máquina).
    $dono = powershell.exe -NoProfile -Command "try { `$m = [Threading.Mutex]::OpenExisting('$nome'); `$m.GetAccessControl().GetOwner([Security.Principal.SecurityIdentifier]).Value } catch { 'nao abriu: ' + `$_.Exception.GetType().Name }"
    $sidUsuario = (Get-LocalUser $usuario).SID.Value
    Write-Output ("dono do mutex: " + $(if ($dono -eq $sidUsuario) { 'o usuario comum' } else { $dono }))
    # E o administrador, com o mutex já criado pelo usuário comum:
    $criado = $false
    $adm = [Threading.Mutex]::new($false, $nome, [ref]$criado)
    Write-Output "administrador depois: criado=$criado (False = ja existia, AppMutex veria o Bench aberto)"
    $adm.Dispose()
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
} finally {
    Remove-LocalUser -Name $usuario
}
