# Funções comuns aos trechos de políticas (ADR-021). Dados só por $env:ITC_*; alvo sempre por SID.
# Saída: linhas `OK|...`, `ERRO|codigo[|politica]`, `DONO|sid` ou JSON. Nunca mensagem do
# Windows: ela pode trazer caminho de perfil.
$HIVE_OK = '^(MAQUINA|S-1-5-21-\d+-\d+-\d+-\d+|ITCBench_[0-9a-f]{8})$'
$RAIZES_USUARIO = @('Software\Policies\', 'Software\Microsoft\Windows\CurrentVersion\Policies\')
$RAIZES_MAQUINA = @('SOFTWARE\Policies\')
$EXATAS_MAQUINA = @('SYSTEM\CurrentControlSet\Services\SharedAccess')
# Perfil (ADR-022): politicas = raízes de política (11); aparencia = só estas chaves exatas e, em
# Policies\System, só os valores Wallpaper e WallpaperStyle (12).
$PERFIL = if ($env:ITC_PERFIL) { $env:ITC_PERFIL } else { 'politicas' }
$EXATAS_APARENCIA = @('Control Panel\Mouse', 'Control Panel\Cursors', 'Control Panel\Keyboard',
    'Control Panel\Accessibility\StickyKeys', 'Control Panel\Accessibility\Keyboard Response',
    'Control Panel\Accessibility\ToggleKeys', 'Software\Microsoft\Accessibility',
    'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')  # modo do Windows (ADR-044)
$CHAVE_PAPEL = 'Software\Microsoft\Windows\CurrentVersion\Policies\System'
$VALORES_PAPEL = @('Wallpaper', 'WallpaperStyle')
$SDDL_NOVA = 'O:BAG:SYD:PAI(A;CI;KA;;;SY)(A;CI;KA;;;BA)(A;CI;KR;;;BU)'
$Vista = [Microsoft.Win32.RegistryView]::Registry64

function Falhar([string]$codigo) { Write-Output ('ERRO|' + $codigo); exit 1 }

function Hive-Formato([string]$hive) { if ($hive -cnotmatch $HIVE_OK) { Falhar 'hive' } }

function So-Papel {
    # ADR-039: todas as operações na chave do papel de parede (mouse e teclado ficam de fora).
    if (-not $env:ITC_OPERACOES) { return $false }
    try { $ops = @($env:ITC_OPERACOES | ConvertFrom-Json | ForEach-Object { $_ }) } catch { return $false }
    if ($ops.Count -eq 0) { return $false }
    foreach ($o in $ops) { if ([string]$o.chave -cne $CHAVE_PAPEL) { return $false } }
    return $true
}

function Hive-Escrita([string]$hive) {
    Hive-Formato $hive
    if ($hive -match '-500$') { Falhar 'nativo' }
    # Conta que roda o Bench, sempre com ITC_PERMITIR_DONO=1: perfil politicas (ADR-034) ou
    # perfil aparencia só com operações do papel de parede (ADR-039).
    $donoOk = ($env:ITC_PERMITIR_DONO -eq '1') -and (
        ($PERFIL -ceq 'politicas') -or (($PERFIL -ceq 'aparencia') -and (So-Papel)))
    if (-not $donoOk -and $hive -eq [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
        Falhar 'dono'
    }
    $prot = @(if ($env:ITC_PROTEGIDOS) { $env:ITC_PROTEGIDOS -split "`n" | Where-Object { $_ } })
    if ($prot -contains $hive) { Falhar 'suporte' }
}

function Raiz-Aceita([string]$hive, [string]$chave) {
    if ($chave -match '\\\\|\.\.|^\\|\\$') { return $false }
    if ($PERFIL -ceq 'aparencia') {
        if ($hive -eq 'MAQUINA') { return $false }
        return ($EXATAS_APARENCIA -contains $chave) -or ($chave -eq $CHAVE_PAPEL)
    }
    if ($PERFIL -cne 'politicas') { return $false }
    if ($hive -eq 'MAQUINA') {
        if ($EXATAS_MAQUINA -contains $chave) { return $true }
        $raizes = $RAIZES_MAQUINA
    } else { $raizes = $RAIZES_USUARIO }
    foreach ($r in $raizes) { if ($chave.StartsWith($r, [StringComparison]::OrdinalIgnoreCase)) { return $true } }
    return $false
}

function Valor-Aceito([string]$chave, [string]$nome) {
    if ($PERFIL -ceq 'aparencia' -and $chave -eq $CHAVE_PAPEL) { return $VALORES_PAPEL -contains $nome }
    return $true
}

function Sob-Politica([string]$chave) {
    foreach ($r in ($RAIZES_USUARIO + $RAIZES_MAQUINA)) {
        if ($chave.StartsWith($r, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function Base([string]$hive) {
    if ($hive -eq 'MAQUINA') { return [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $Vista) }
    $u = [Microsoft.Win32.RegistryKey]::OpenBaseKey('Users', $Vista)
    $k = $u.OpenSubKey($hive, $true)
    if (-not $k) { $k = $u.OpenSubKey($hive, $false) }
    if (-not $k) { Falhar 'hive_ausente' }
    return $k
}
