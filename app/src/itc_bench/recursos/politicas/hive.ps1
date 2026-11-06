# Carrega e descarrega o NTUSER.DAT de um perfil em HKU\ITCBench_<hex> (ADR-021).
# $env:ITC_ACAO = carregar | descarregar | sobras; $env:ITC_SID = SID ou DEFAULT; $env:ITC_HIVE.
# O caminho do perfil é lido e conferido aqui; nunca sai deste trecho nem vai para a saída.
$reg = Join-Path ([Environment]::GetFolderPath('System')) 'reg.exe'
$TEMP = '^ITCBench_[0-9a-f]{8}$'

function Reg([string[]]$argumentos) {
    $ErrorActionPreference = 'Continue'
    & $reg @argumentos 2>&1 | Out-Null
    return $LASTEXITCODE
}

function Descarregar([string]$nome) {
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    return (Reg @('unload', ('HKU\' + $nome)))
}

switch ($env:ITC_ACAO) {
    'sobras' {
        Write-Output ('DONO|' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
        $u = [Microsoft.Win32.RegistryKey]::OpenBaseKey('Users', $Vista)
        foreach ($n in $u.GetSubKeyNames()) {
            if ($n -cmatch $TEMP) {
                if (Descarregar $n) { Write-Output 'SOBRA|falhou' } else { Write-Output 'SOBRA|ok' }
            }
        }
        $u.Close()
    }
    'carregar' {
        if ($env:ITC_HIVE -cnotmatch $TEMP) { Falhar 'hive' }
        $lista = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $Vista).OpenSubKey(
            'SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList', $false)
        if ($env:ITC_SID -ceq 'DEFAULT') {
            $pasta = [Environment]::ExpandEnvironmentVariables([string]$lista.GetValue('Default'))
        } else {
            Hive-Escrita $env:ITC_SID
            if ([Microsoft.Win32.RegistryKey]::OpenBaseKey('Users', $Vista).OpenSubKey($env:ITC_SID)) { Falhar 'carregado' }
            $p = $lista.OpenSubKey($env:ITC_SID, $false)
            if (-not $p) { Falhar 'sem_perfil' }
            $pasta = [Environment]::ExpandEnvironmentVariables([string]$p.GetValue('ProfileImagePath'))
        }
        if (-not $pasta) { Falhar 'sem_perfil' }
        $usuarios = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetPathRoot([Environment]::GetFolderPath('System'))) 'Users')).TrimEnd('\') + '\'
        $pasta = [IO.Path]::GetFullPath($pasta)
        if (-not $pasta.StartsWith($usuarios, [StringComparison]::OrdinalIgnoreCase)) { Falhar 'perfil_fora' }
        if ((Split-Path $pasta -Leaf) -match '^TEMP') { Falhar 'perfil_temporario' }
        $arquivo = Join-Path $pasta 'NTUSER.DAT'
        if (-not (Test-Path -LiteralPath $arquivo -PathType Leaf)) { Falhar 'sem_perfil' }
        if (Reg @('load', ('HKU\' + $env:ITC_HIVE), $arquivo)) { Falhar 'em_uso' }
        Write-Output 'OK'
    }
    'descarregar' {
        if ($env:ITC_HIVE -cnotmatch $TEMP) { Falhar 'hive' }
        if (Descarregar $env:ITC_HIVE) { Falhar 'descarregar' }
        Write-Output 'OK'
    }
    default { Falhar 'acao' }
}
