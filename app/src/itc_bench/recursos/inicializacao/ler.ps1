# Inicialização (ADR-075), leitura: só lê. Programas do Run e da pasta Inicializar (máquina e
# cada conta), apps da Loja com tarefa de inicialização, tarefas agendadas de logon ou boot fora da
# Microsoft, serviços automáticos fora do Windows e os eventos de tempo de boot. Saída em JSON.
$itens = New-Object System.Collections.ArrayList

function Item($tipo, $sid, $conta, $nome, $comando, $ativo) {
    [void]$itens.Add([ordered]@{ tipo = $tipo; sid = $sid; conta = $conta; nome = [string]$nome; comando = [string]$comando; ativo = [bool]$ativo })
}

function Ler-Run($base, $caminho, $aprov, $tipo, $sid, $conta) {
    $k = Sub $base $caminho
    if (-not $k) { return }
    $a = Sub $base $aprov
    foreach ($n in $k.GetValueNames()) {
        if (-not $n) { continue }
        Item $tipo $sid $conta $n $k.GetValue($n) (-not (Desligado $a $n))
    }
}

function Ler-Pasta($pasta, $base, $aprov, $tipo, $sid, $conta) {
    if (-not (Test-Path -LiteralPath $pasta -ErrorAction SilentlyContinue)) { return }
    $a = Sub $base $aprov
    foreach ($f in Get-ChildItem -LiteralPath $pasta -File -Force -ErrorAction SilentlyContinue) {
        if ($f.Name -ieq 'desktop.ini') { continue }
        Item $tipo $sid $conta $f.Name $f.Name (-not (Desligado $a $f.Name))
    }
}

try {
    Ler-Run $HKLM $RUN "$APROV\Run" 'run' 'MAQUINA' ''
    Ler-Run $HKLM $RUN32 "$APROV\Run32" 'run32' 'MAQUINA' ''
    Ler-Pasta ([Environment]::GetFolderPath('CommonStartup')) $HKLM "$APROV\StartupFolder" 'pasta' 'MAQUINA' ''

    foreach ($c in Contas) {
      try {
        $h = Hive-Usuario $c
        if ($h) {
            $u = Sub $HKU $h
            if ($u) {
                Ler-Run $u $RUN "$APROV\Run" 'runuser' $c.Sid $c.Nome
                Ler-Pasta (Join-Path $c.Pasta $PASTA_USUARIO) $u "$APROV\StartupFolder" 'pastauser' $c.Sid $c.Nome
            }
        }
        $h = Hive-Classes $c
        $apps = if ($h) { Sub $HKU "$h\$RAIZ_APPS" } else { $null }
        if ($apps) {
            foreach ($pkg in $apps.GetSubKeyNames()) {
                $kp = $null
                try { $kp = Sub $apps $pkg } catch { continue }
                if (-not $kp) { continue }
                foreach ($t in $kp.GetSubKeyNames()) {
                    $estado = $null
                    try { $estado = (Sub $kp $t).GetValue('State') } catch { continue }
                    if ($null -eq $estado) { continue }
                    # 2 = ligado, 4 = ligado por política; 0, 1 e 3 = desligado.
                    Item 'app' $c.Sid $c.Nome "$pkg\$t" ($pkg -replace '_.*$', '') ($estado -eq 2 -or $estado -eq 4)
                }
            }
        }
      } catch { Item 'erro' $c.Sid $c.Nome 'conta' '' $false }
    }

    foreach ($t in Get-ScheduledTask -ErrorAction SilentlyContinue) {
        if ($t.TaskPath -like '\Microsoft\*') { continue }
        $gatilho = $t.Triggers | Where-Object { $_.CimClass.CimClassName -match 'Logon|Boot' }
        if (-not $gatilho) { continue }
        $cmd = ($t.Actions | ForEach-Object { ([string]$_.Execute + ' ' + [string]$_.Arguments).Trim() }) -join ' ; '
        Item 'tarefa' 'MAQUINA' '' ($t.TaskPath + $t.TaskName) $cmd ($t.State -ne 'Disabled')
    }
} finally {
    Fechar-Hives
}

$servicos = @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object {
    $_.StartMode -eq 'Auto' -and $_.PathName -and $_.PathName -notmatch '\\Windows\\(System32|SysWOW64|servicing)\\'
} | ForEach-Object { [ordered]@{ nome = [string]$_.DisplayName; rodando = ($_.State -eq 'Running'); comando = [string]$_.PathName } })

function Dados($e) {
    $d = @{}
    foreach ($x in ([xml]$e.ToXml()).Event.EventData.Data) { $d[$x.Name] = $x.'#text' }
    return $d
}

$log = 'Microsoft-Windows-Diagnostics-Performance/Operational'
$boots = @(Get-WinEvent -FilterHashtable @{ LogName = $log; Id = 100 } -MaxEvents 5 -ErrorAction SilentlyContinue | ForEach-Object {
    $d = Dados $_
    [ordered]@{ data = $_.TimeCreated.ToString('s'); boot_ms = [long]$d.BootTime; pos_ms = [long]$d.BootPostBootTime }
})
$desde = (Get-Date).AddDays(-30)
$atrasos = @(Get-WinEvent -FilterHashtable @{ LogName = $log; Id = 101..110; StartTime = $desde } -MaxEvents 200 -ErrorAction SilentlyContinue | ForEach-Object {
    $d = Dados $_
    $nome = @($d.FriendlyName, $d.Name, $d.FileName) | Where-Object { $_ } | Select-Object -First 1
    [ordered]@{ data = $_.TimeCreated.ToString('s'); nome = [string]$nome; atraso_ms = [long]$d.DegradationTime }
} | Sort-Object { $_.atraso_ms } -Descending | Select-Object -First 15)

[ordered]@{ itens = @($itens); servicos = $servicos; boots = $boots; atrasos = $atrasos } | ConvertTo-Json -Depth 4 -Compress
