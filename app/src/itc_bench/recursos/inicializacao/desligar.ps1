# Inicialização (ADR-075), desligar: ITC_ITENS = JSON [{tipo, sid, nome}], escolhidos na tela a
# partir da leitura. Cada item é conferido de novo aqui (existe, tipo e conta válidos, não é
# essencial) e desligado do jeito que o Windows desliga: StartupApproved (o mesmo do Gerenciador
# de Tarefas), State=1 da tarefa do app da Loja ou tarefa agendada desativada. Nada é apagado.
$DESLIGADO = [byte[]](3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
$pedidos = ConvertFrom-Json -InputObject $env:ITC_ITENS  # PS 5.1: array chega inteiro; o foreach abre
$contas = @{}
foreach ($c in Contas) { $contas[$c.Sid] = $c }
$saida = New-Object System.Collections.ArrayList

function Marcar($base, $sub, $nome) {
    $k = $base.CreateSubKey($sub)
    $k.SetValue($nome, $DESLIGADO, [Microsoft.Win32.RegistryValueKind]::Binary)
    $k.Close()
}

function Desligar($p) {
    $tipo = [string]$p.tipo; $sid = [string]$p.sid; $nome = [string]$p.nome
    if (-not $nome -or $nome -match $ESSENCIAL) { return 'essencial' }
    if ($tipo -in @('run', 'run32', 'pasta', 'tarefa')) {
        if ($sid -cne 'MAQUINA') { return 'invalido' }
    } elseif ($tipo -in @('runuser', 'pastauser', 'app')) {
        if (-not $contas.ContainsKey($sid)) { return 'sem_conta' }
        $c = $contas[$sid]
    } else { return 'invalido' }

    switch ($tipo) {
        'run' {
            if ($null -eq $HKLM.OpenSubKey($RUN).GetValue($nome)) { return 'sumiu' }
            Marcar $HKLM "$APROV\Run" $nome
        }
        'run32' {
            $k = $HKLM.OpenSubKey($RUN32)
            if (-not $k -or $null -eq $k.GetValue($nome)) { return 'sumiu' }
            Marcar $HKLM "$APROV\Run32" $nome
        }
        'pasta' {
            if ($nome -match '[\\/]' -or -not (Test-Path -LiteralPath (Join-Path ([Environment]::GetFolderPath('CommonStartup')) $nome))) { return 'sumiu' }
            Marcar $HKLM "$APROV\StartupFolder" $nome
        }
        'runuser' {
            $h = Hive-Usuario $c
            if (-not $h) { return 'conta_em_uso' }
            $k = Sub $HKU "$h\$RUN"
            if (-not $k -or $null -eq $k.GetValue($nome)) { return 'sumiu' }
            Marcar $HKU "$h\$APROV\Run" $nome
        }
        'pastauser' {
            $h = Hive-Usuario $c
            if (-not $h) { return 'conta_em_uso' }
            if ($nome -match '[\\/]' -or -not (Test-Path -LiteralPath (Join-Path (Join-Path $c.Pasta $PASTA_USUARIO) $nome))) { return 'sumiu' }
            Marcar $HKU "$h\$APROV\StartupFolder" $nome
        }
        'app' {
            if ($nome -notmatch '^[^\\]+\\[^\\]+$') { return 'invalido' }
            $h = Hive-Classes $c
            if (-not $h) { return 'conta_em_uso' }
            $k = Sub $HKU "$h\$RAIZ_APPS\$nome" $true
            if (-not $k -or $null -eq $k.GetValue('State')) { return 'sumiu' }
            $k.SetValue('State', 1, [Microsoft.Win32.RegistryValueKind]::DWord)
        }
        'tarefa' {
            $i = $nome.LastIndexOf('\')
            if ($i -lt 0 -or $nome -like '\Microsoft\*') { return 'invalido' }
            $t = Get-ScheduledTask -TaskPath $nome.Substring(0, $i + 1) -TaskName $nome.Substring($i + 1) -ErrorAction SilentlyContinue
            if (-not $t) { return 'sumiu' }
            $t | Disable-ScheduledTask | Out-Null
        }
    }
    return ''
}

try {
    foreach ($p in $pedidos) {
        try { $codigo = Desligar $p } catch { $codigo = 'falhou' }
        [void]$saida.Add([ordered]@{ tipo = [string]$p.tipo; sid = [string]$p.sid; nome = [string]$p.nome; codigo = $codigo })
    }
} finally {
    Fechar-Hives
}
ConvertTo-Json -InputObject @($saida) -Depth 3 -Compress
