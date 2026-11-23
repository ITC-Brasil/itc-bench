# Inicialização (ADR-075): partes comuns de ler.ps1 e desligar.ps1, que vêm logo depois.
# Contas pelo ProfileList (só pastas dentro de Users); hive de conta fora da sessão carregado em
# HKU\ITCBench_<hex> e sempre descarregado no fim (a sobra é limpa como no ADR-021).
$Vista = [Microsoft.Win32.RegistryView]::Registry64
$HKLM = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $Vista)
$HKU = [Microsoft.Win32.RegistryKey]::OpenBaseKey('Users', $Vista)
$reg = Join-Path ([Environment]::GetFolderPath('System')) 'reg.exe'
$RUN = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
$RUN32 = 'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'
$APROV = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved'
$RAIZ_APPS = 'Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData'
$PASTA_USUARIO = 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup'
# Nunca desligados: acesso remoto, inventário, antivírus, áudio e o próprio Bench.
$ESSENCIAL = '(?i)anydesk|rustdesk|glpi|securityhealth|windows ?defender|rtkaud|itc.?bench'
$script:carregados = @()
$script:mapa = @{}  # nome do hive -> HKU\ITCBench_<hex> já carregado nesta execução
# Toda chave aberta fica aqui e é fechada antes do unload: chave aberta prende o hive.
$script:abertas = New-Object System.Collections.ArrayList

function Reg-Exe([string[]]$argumentos) {
    $ErrorActionPreference = 'Continue'
    & $reg @argumentos 2>&1 | Out-Null
    return $LASTEXITCODE
}

function Sub($base, [string]$caminho, [bool]$escrita = $false) {
    if (-not $base) { return $null }
    $k = $base.OpenSubKey($caminho, $escrita)
    if ($k) { [void]$script:abertas.Add($k) }
    return $k
}

function Limpar-Sobras {
    # Hive de uma execução que não conseguiu descarregar (ADR-021): descarrega antes de começar.
    foreach ($n in $HKU.GetSubKeyNames()) {
        if ($n -cmatch '^ITCBench_[0-9a-f]{8}$') { Reg-Exe @('unload', ('HKU\' + $n)) | Out-Null }
    }
}

function Contas {
    $lista = $HKLM.OpenSubKey('SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList')
    $raiz = Join-Path ([IO.Path]::GetPathRoot([Environment]::GetFolderPath('System'))) 'Users'
    $usuarios = [IO.Path]::GetFullPath($raiz).TrimEnd('\') + '\'
    foreach ($sid in $lista.GetSubKeyNames()) {
        if ($sid -notmatch '^S-1-5-21-[0-9-]+$') { continue }
        $bruto = [string]$lista.OpenSubKey($sid).GetValue('ProfileImagePath')
        if (-not $bruto) { continue }
        $pasta = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($bruto))
        if (-not $pasta.StartsWith($usuarios, [StringComparison]::OrdinalIgnoreCase)) { continue }
        if ((Split-Path $pasta -Leaf) -match '^TEMP') { continue }
        [pscustomobject]@{ Sid = $sid; Nome = (Split-Path $pasta -Leaf); Pasta = $pasta }
    }
}

function Abrir-Hive([string]$nome, [string]$arquivo) {
    # Hive já carregado (conta com sessão) ou carregado agora; $null se não deu.
    $ja = $HKU.OpenSubKey($nome)
    if ($ja) { $ja.Close(); return $nome }
    # Já carregado por esta execução (outro item da mesma conta): reaproveita. Carregar de novo
    # falharia, porque o próprio Bench está com o arquivo aberto.
    if ($script:mapa.ContainsKey($nome)) { return $script:mapa[$nome] }
    if (-not (Test-Path -LiteralPath $arquivo -PathType Leaf -ErrorAction SilentlyContinue)) { return $null }
    try { ([IO.File]::Open($arquivo, 'Open', 'Read', 'None')).Close() } catch { return $null }
    $tmp = 'ITCBench_' + ('{0:x8}' -f (Get-Random -Minimum 0 -Maximum ([int]::MaxValue)))
    if (Reg-Exe @('load', ('HKU\' + $tmp), $arquivo)) { return $null }
    $script:carregados += $tmp
    $script:mapa[$nome] = $tmp
    return $tmp
}

function Hive-Usuario($c) { Abrir-Hive $c.Sid (Join-Path $c.Pasta 'NTUSER.DAT') }
function Hive-Classes($c) { Abrir-Hive ($c.Sid + '_Classes') (Join-Path $c.Pasta 'AppData\Local\Microsoft\Windows\UsrClass.dat') }

function Fechar-Hives {
    foreach ($k in $script:abertas) { try { $k.Close() } catch { $k = $null } }
    $script:abertas.Clear()
    foreach ($h in $script:carregados) {
        for ($n = 0; $n -lt 5; $n++) {
            [GC]::Collect(); [GC]::WaitForPendingFinalizers()
            if (-not (Reg-Exe @('unload', ('HKU\' + $h)))) { break }
            Start-Sleep -Milliseconds 300
        }
    }
}

Limpar-Sobras

function Desligado($chave, [string]$nome) {
    # StartupApproved: primeiro byte ímpar = desligado (o que o Gerenciador de Tarefas grava).
    if (-not $chave) { return $false }
    $v = $chave.GetValue($nome)
    return ($v -is [byte[]]) -and ($v.Length -gt 0) -and (($v[0] % 2) -eq 1)
}
