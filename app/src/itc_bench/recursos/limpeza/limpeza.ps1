# Limpeza de manutenção (ADR-023). ITC_ACAO: previa | limpar. ITC_ITENS: ids separados por vírgula.
# Raízes fixas; nunca desce em reparse point (o link é removido como link); cada caminho conferido
# contra a raiz. Saída só com números por id, nunca caminho.
$win = [Environment]::GetFolderPath('Windows')
$sysdrive = [IO.Path]::GetPathRoot($win)
$usuarios = Join-Path $sysdrive 'Users'
$RP = [IO.FileAttributes]::ReparsePoint
$apagar = $env:ITC_ACAO -eq 'limpar'
if (-not $apagar -and $env:ITC_ACAO -ne 'previa') { throw 'acao invalida' }

function Eh-Reparse([string]$c) {
    $i = Get-Item -LiteralPath $c -Force -ErrorAction SilentlyContinue
    return ($null -eq $i) -or (($i.Attributes -band $RP) -ne 0)
}

function Varrer([string]$raiz, $acc) {
    $di = New-Object IO.DirectoryInfo $raiz
    if (-not $di.Exists) { return }
    if (($di.Attributes -band $RP) -ne 0) { $acc.codigo = 'reparse'; return }
    $prefixo = $di.FullName.TrimEnd('\') + '\'
    $pilha = New-Object System.Collections.Stack
    $pilha.Push($di)
    $dirs = New-Object System.Collections.ArrayList
    while ($pilha.Count -gt 0) {
        $d = $pilha.Pop()
        try { $itens = @($d.GetFileSystemInfos()) } catch { $acc.em_uso++; continue }
        foreach ($i in $itens) {
            if (-not $i.FullName.StartsWith($prefixo, [StringComparison]::OrdinalIgnoreCase)) { $acc.codigo = 'fora'; continue }
            if (($i.Attributes -band $RP) -ne 0) {
                if ($apagar) {
                    try { if ($i -is [IO.DirectoryInfo]) { [IO.Directory]::Delete($i.FullName, $false) } else { $i.Delete() } }
                    catch { $acc.em_uso++ }
                }
                continue
            }
            if ($i -is [IO.DirectoryInfo]) { $pilha.Push($i); [void]$dirs.Add($i); continue }
            $acc.arquivos++
            $acc.bytes += $i.Length
            if ($apagar) {
                try { $i.Attributes = [IO.FileAttributes]::Normal; $i.Delete() } catch { $acc.em_uso++ }
            }
        }
    }
    if ($apagar) {
        for ($k = $dirs.Count - 1; $k -ge 0; $k--) {
            try { $dirs[$k].Delete($false) } catch { $acc.pastas_restantes++ }
        }
    }
}

function Raizes([string]$id) {
    switch ($id) {
        'temp_sistema' { return @(Join-Path $win 'Temp') }
        'relatorios_erro' {
            $wer = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'Microsoft\Windows\WER'
            return @((Join-Path $wer 'ReportArchive'), (Join-Path $wer 'ReportQueue'))
        }
        'windows_update' { return @(Join-Path $win 'SoftwareDistribution\Download') }
        'lixeira' {
            $r = @()
            foreach ($disco in @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3')) {
                $bin = $disco.DeviceID + '\$Recycle.Bin'
                if (-not (Test-Path -LiteralPath $bin) -or (Eh-Reparse $bin)) { continue }
                $r += @(Get-ChildItem -LiteralPath $bin -Force -Directory | Where-Object {
                    $_.Name -match '^S-1-5-21-[\d-]+$' -and (($_.Attributes -band $RP) -eq 0) } | ForEach-Object { $_.FullName })
            }
            return $r
        }
        'temp_usuarios' {
            $r = @()
            $lista = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList'
            foreach ($k in @(Get-ChildItem -LiteralPath $lista | Where-Object { $_.PSChildName -match '^S-1-5-21-[\d-]+$' })) {
                $perfil = [Environment]::ExpandEnvironmentVariables([string]$k.GetValue('ProfileImagePath'))
                if (-not $perfil.StartsWith($usuarios + '\', [StringComparison]::OrdinalIgnoreCase)) { continue }
                if ((Split-Path $perfil -Leaf) -match '^TEMP') { continue }
                $passos = @($perfil, (Join-Path $perfil 'AppData'), (Join-Path $perfil 'AppData\Local'), (Join-Path $perfil 'AppData\Local\Temp'))
                if (@($passos | Where-Object { Eh-Reparse $_ }).Count -gt 0) { continue }
                $r += $passos[3]
            }
            return $r
        }
        default { throw 'item invalido' }
    }
}

$saida = @()
foreach ($id in @($env:ITC_ITENS -split ',' | Where-Object { $_ })) {
    $acc = @{ id = $id; arquivos = 0; bytes = [int64]0; em_uso = 0; pastas_restantes = 0; codigo = ''; limpo = $true }
    $servicos = @()
    try {
        if ($apagar -and $id -eq 'windows_update') {
            $chave = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
            if (Test-Path -LiteralPath $chave) { $acc.codigo = 'reinicio_pendente'; $acc.limpo = $false; $saida += $acc; continue }
            foreach ($nome in @('wuauserv', 'bits')) {
                $s = Get-Service -Name $nome
                if ($s.Status -ne 'Stopped') {
                    $servicos += $nome
                    $s.Stop()
                    $s.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(60))
                }
            }
        }
        foreach ($raiz in @(Raizes $id)) { Varrer $raiz $acc }
    } catch [System.ServiceProcess.TimeoutException] {
        $acc.codigo = 'servico_nao_parou'; $acc.limpo = $false
    } catch {
        $acc.codigo = 'erro_' + $_.Exception.GetType().Name; $acc.limpo = $false
    } finally {
        foreach ($nome in $servicos) {
            try { Start-Service -Name $nome } catch { $acc.codigo = 'servico_nao_voltou'; $acc.limpo = $false }
        }
    }
    if ($acc.codigo -in @('reparse', 'fora')) { $acc.limpo = $false }
    $saida += $acc
}
ConvertTo-Json -Compress -InputObject @($saida | ForEach-Object { [pscustomobject]$_ })
